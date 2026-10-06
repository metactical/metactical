import datetime as dt
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from metactical.time_tracker import api, core

USER = "tc.worker@example.com"
APPROVER = "tc.approver@example.com"
DAY = dt.date(2026, 10, 7)  # a Wednesday, inside the test pay cycle


def at(h, m=0, day=DAY):
	return dt.datetime.combine(day, dt.time(h, m))


def shift(start, end):
	return SimpleNamespace(start_time=dt.timedelta(hours=start), end_time=dt.timedelta(hours=end))


class TestShiftWindow(FrappeTestCase):
	"""Pure rules, no database."""

	def test_day_shift_states(self):
		s = shift(9, 17)
		self.assertEqual(core.shift_window(s, at(8, 30), 15)[0], "before")
		self.assertEqual(core.shift_window(s, at(8, 45), 15)[0], "open")  # exactly 15 min early
		self.assertEqual(core.shift_window(s, at(12), 15)[0], "open")
		self.assertEqual(core.shift_window(s, at(17), 15)[0], "open")
		self.assertEqual(core.shift_window(s, at(17, 1), 15)[0], "after")

	def test_overnight_shift_is_open_after_midnight(self):
		s = shift(22, 6)
		state, start, end = core.shift_window(s, at(1), 15)
		self.assertEqual(state, "open")
		self.assertEqual(start, at(22, day=DAY - dt.timedelta(days=1)))
		self.assertEqual(end, at(6))
		self.assertEqual(core.shift_window(s, at(23), 15)[0], "open")
		self.assertEqual(core.shift_window(s, at(12), 15)[0], "before")

	def test_to_timedelta_accepts_every_frappe_shape(self):
		for v in (dt.timedelta(hours=9, minutes=30), dt.time(9, 30), "9:30:00", "09:30"):
			self.assertEqual(core.to_timedelta(v), dt.timedelta(hours=9, minutes=30))

	def test_negative_duration_is_not_flipped(self):
		self.assertLess(core.hours_between(at(17), at(9)), 0)


class TestClockFlow(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.company = frappe.db.get_value("Company", {}, "name") or cls._make_company()
		for email, first in ((USER, "Worker"), (APPROVER, "Approver")):
			if not frappe.db.exists("User", email):
				frappe.get_doc(
					{"doctype": "User", "email": email, "first_name": first, "send_welcome_email": 0,
					 "roles": [{"role": "Employee"}]}
				).insert(ignore_permissions=True)
		cls.employee = cls._make_employee(USER, "Worker")
		if not frappe.db.exists("Shift Type", "TC Day"):
			frappe.get_doc(
				{"doctype": "Shift Type", "name": "TC Day", "start_time": "09:00:00", "end_time": "17:00:00"}
			).insert(ignore_permissions=True)
		if not frappe.db.exists("Shift Assignment", {"employee": cls.employee, "docstatus": 1, "status": "Active"}):
			sa = frappe.get_doc(
				{"doctype": "Shift Assignment", "employee": cls.employee, "shift_type": "TC Day",
				 "company": cls.company, "start_date": "2026-01-01", "status": "Active"}
			).insert(ignore_permissions=True)
			sa.submit()
		s = frappe.get_doc("Time Tracker Settings")
		cls._saved_settings = s.as_dict(convert_dates_to_str=True)  # put back in tearDownClass
		s.checkin_approver = APPROVER
		s.start_date = "2026-09-03"
		s.set("pay_cycles", [{"from_date": "2026-09-03", "to_date": "2026-09-16"}, {"from_date": "2026-09-17", "to_date": "2026-09-30"}, {"from_date": "2026-10-01", "to_date": "2026-10-14"}])
		s.early_clockin_minutes = 15
		s.enforce_shift_window = 1
		s.max_shift_hours = 16
		s.reminder_minutes_after_shift_end = 15
		s.auto_close_hours_after_shift_end = 2
		s.save(ignore_permissions=True)
		frappe.clear_cache()

	@classmethod
	def tearDownClass(cls):
		"""The tests rewrite Time Tracker Settings; leave the site's own settings as they were."""
		frappe.set_user("Administrator")
		saved = getattr(cls, "_saved_settings", None)
		if saved:
			s = frappe.get_doc("Time Tracker Settings")
			for f in ("checkin_approver", "start_date", "logout_delay", "early_clockin_minutes",
					  "enforce_shift_window", "max_shift_hours", "backdate_limit_days", "standard_day_hours",
					  "reminder_minutes_after_shift_end", "auto_close_hours_after_shift_end"):
				s.set(f, saved.get(f))
			s.set("pay_cycles", [{"from_date": r["from_date"], "to_date": r["to_date"]} for r in saved.get("pay_cycles", [])])
			s.save(ignore_permissions=True)
			frappe.db.commit()
		super().tearDownClass()

	@classmethod
	def _make_company(cls):
		return frappe.get_doc(
			{"doctype": "Company", "company_name": "TC Co", "abbr": "TC", "default_currency": "CAD", "country": "Canada"}
		).insert(ignore_permissions=True).name

	@classmethod
	def _make_employee(cls, email, first):
		existing = frappe.db.get_value("Employee", {"user_id": email})
		if existing:
			return existing
		return frappe.get_doc(
			{"doctype": "Employee", "first_name": first, "gender": "Other", "date_of_birth": "1990-01-01",
			 "date_of_joining": "2020-01-01", "company": cls.company, "status": "Active", "user_id": email}
		).insert(ignore_permissions=True).name

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.delete("Clockin Log", {"user": USER})
		frappe.db.delete("Checkin Request Modification", {"user": USER})
		frappe.db.delete("Employee Checkin", {"employee": self.employee})  # HRMS refuses duplicate timestamps
		frappe.db.delete("Pay Cycle", {"user": USER})
		frappe.set_user(USER)

	def tearDown(self):
		frappe.set_user("Administrator")

	def clock(self, fn, when):
		with patch("metactical.time_tracker.core.now_datetime", return_value=when):
			return getattr(api, fn)()

	def state(self, when):
		with patch("metactical.time_tracker.core.now_datetime", return_value=when):
			return api.get_state()

	def test_full_day_uses_server_time_and_adds_up(self):
		s = self.clock("clock_in", at(9, 2))
		self.assertEqual(s["status"], "in")
		self.assertEqual(s["open_log"]["from_time"][:16], "2026-10-07T09:02")  # ISO, with the server offset after it
		s = self.clock("clock_out", at(17, 0))
		self.assertEqual(s["status"], "out")
		self.assertAlmostEqual(s["today"]["total_hours"], 7 + 58 / 60, places=3)
		self.assertAlmostEqual(s["cycle"]["total_hours"], 7 + 58 / 60, places=3)

	def test_double_tap_does_not_create_two_open_logs(self):
		self.clock("clock_in", at(9, 0))
		s = self.clock("clock_in", at(9, 0))
		self.assertIn("already", s["notice"].lower())
		self.assertEqual(frappe.db.count("Clockin Log", {"user": USER, "has_clocked_out": 0}), 1)

	def test_clock_out_when_not_in_is_harmless(self):
		s = self.clock("clock_out", at(12))
		self.assertEqual(s["status"], "out")

	def test_too_early_is_refused_with_a_reason(self):
		s = self.state(at(7, 0))
		self.assertFalse(s["can_clock_in"])
		self.assertIn("9:00", s["can_clock_in_reason"])
		with self.assertRaises(frappe.ValidationError):
			self.clock("clock_in", at(7, 0))

	def test_pay_cycle_document_stays_in_step(self):
		self.clock("clock_in", at(9, 0))
		self.clock("clock_out", at(13, 0))
		name = frappe.db.get_value("Pay Cycle", {"user": USER, "from_date": "2026-10-01"})
		self.assertTrue(name)
		days = {str(d.date): d.hours_worked for d in frappe.get_doc("Pay Cycle", name).days}
		self.assertEqual(len(days), 14)
		self.assertAlmostEqual(days["2026-10-07"], 4.0, places=3)

	def test_user_without_employee_is_told_why(self):
		frappe.set_user("Administrator")
		if not frappe.db.exists("User", "tc.nobody@example.com"):
			frappe.get_doc({"doctype": "User", "email": "tc.nobody@example.com", "first_name": "Nobody",
							"send_welcome_email": 0, "roles": [{"role": "Employee"}]}).insert(ignore_permissions=True)
		frappe.set_user("tc.nobody@example.com")
		s = api.get_state()
		self.assertEqual(s["status"], "blocked")
		self.assertEqual(s["blockers"][0]["code"], "no_employee")

	def test_negative_log_is_rejected(self):
		log = frappe.get_doc({"doctype": "Clockin Log", "user": USER, "date": DAY, "from_time": at(17),
							  "to_time": at(9), "has_clocked_out": 1})
		with self.assertRaises(frappe.ValidationError):
			log.insert(ignore_permissions=True)

	def _closed_log(self):
		self.clock("clock_in", at(9, 0))
		self.clock("clock_out", at(17, 0))
		return frappe.db.get_value("Clockin Log", {"user": USER}, "name")

	def test_correction_needs_a_reason_and_valid_times(self):
		log = self._closed_log()
		with self._now(at(18)):
			with self.assertRaises(frappe.ValidationError):
				api.request_correction(log, "2026-10-07 09:00:00", "2026-10-07 17:00:00", "")
			with self.assertRaises(frappe.ValidationError):
				api.request_correction(log, "2026-10-07 17:00:00", "2026-10-07 09:00:00", "swapped")

	def test_only_the_approver_can_approve_and_never_their_own(self):
		log = self._closed_log()
		with self._now(at(18)):
			req = api.request_correction(log, "2026-10-07 08:55:00", "2026-10-07 17:30:00", "Stayed late")["name"]
		with self.assertRaises(frappe.PermissionError):  # the requester is not the approver
			api.review_request(req, "Approved")
		frappe.set_user(APPROVER)
		api.review_request(req, "Approved", "ok")
		row = frappe.db.get_value("Clockin Log", log, ["from_time", "to_time", "total_hours"], as_dict=True)
		self.assertEqual(str(row.from_time)[:16], "2026-10-07 08:55")
		self.assertAlmostEqual(row.total_hours, 8 + 35 / 60, places=3)
		with self.assertRaises(frappe.ValidationError):  # already decided
			api.review_request(req, "Declined")

	def test_employee_cannot_edit_or_delete_their_own_log_through_the_api(self):
		log = self._closed_log()
		self.assertFalse(frappe.has_permission("Clockin Log", "write", log, user=USER))
		self.assertFalse(frappe.has_permission("Clockin Log", "delete", log, user=USER))
		self.assertTrue(frappe.has_permission("Clockin Log", "read", log, user=USER))

	def test_cycle_scales_to_shift_and_flags_short_days(self):
		# 8h shift. A 4h day is short, a full 8h day is not, and an in-progress or empty day is never short.
		for day, h1, h2 in ((dt.date(2026, 10, 5), 9, 13), (dt.date(2026, 10, 6), 9, 17)):
			self.clock_on(day, h1, h2)
		with patch("metactical.time_tracker.core.now_datetime", return_value=at(12)):
			cycle = api.get_cycle()
		self.assertEqual(cycle["expected_hours"], 8.0)
		by_date = {d["date"]: d for d in cycle["days"]}
		self.assertTrue(by_date["2026-10-05"]["short"])
		self.assertFalse(by_date["2026-10-06"]["short"])
		self.assertFalse(by_date["2026-10-03"]["short"])  # nothing worked
		self.assertFalse(by_date["2026-10-07"]["short"])  # today

	def clock_on(self, day, h1, h2):
		self.clock("clock_in", at(h1, day=day))
		self.clock("clock_out", at(h2, day=day))

	# ---- missed days -------------------------------------------------------------------------

	def _now(self, when):
		return patch("metactical.time_tracker.core.now_datetime", return_value=when)

	def test_missed_day_can_be_requested_and_approved(self):
		day = dt.date(2026, 10, 5)  # Monday, nothing clocked
		with self._now(at(12)):
			req = api.request_missed_punch(str(day), "2026-10-05 09:00:00", "2026-10-05 17:00:00", "Forgot to clock in")
			cycle = api.get_cycle()
		d = {x["date"]: x for x in cycle["days"]}["2026-10-05"]
		self.assertEqual(d["pending_requests"], 1)
		self.assertFalse(frappe.db.exists("Clockin Log", {"user": USER, "date": day}))  # nothing counted yet
		frappe.set_user(APPROVER)
		with self._now(at(12)):
			api.review_request(req["name"], "Approved")
		row = frappe.db.get_value("Clockin Log", {"user": USER, "date": day}, ["total_hours", "has_clocked_out"], as_dict=True)
		self.assertEqual((row.total_hours, row.has_clocked_out), (8.0, 1))
		self.assertTrue(frappe.db.exists("Employee Checkin", {"employee": self.employee, "log_type": "OUT"}))

	def test_missed_day_rules(self):
		with self._now(at(12)):
			args = ("2026-10-05", "2026-10-05 09:00:00", "2026-10-05 17:00:00", "Forgot")
			with self.assertRaises(frappe.ValidationError):  # no reason
				api.request_missed_punch("2026-10-05", args[1], args[2], "")
			with self.assertRaises(frappe.ValidationError):  # future day
				api.request_missed_punch("2026-10-09", "2026-10-09 09:00:00", "2026-10-09 17:00:00", "x y z")
			with self.assertRaises(frappe.ValidationError):  # too far back
				api.request_missed_punch("2026-09-01", "2026-09-01 09:00:00", "2026-09-01 17:00:00", "too old")
			with self.assertRaises(frappe.ValidationError):  # clock in not on the chosen day
				api.request_missed_punch("2026-10-05", "2026-10-04 09:00:00", "2026-10-05 17:00:00", "wrong day")
			api.request_missed_punch(*args)
			with self.assertRaises(frappe.ValidationError):  # one waiting request per day
				api.request_missed_punch(*args)

	def test_missed_time_cannot_overlap_existing_entry(self):
		self.clock_on(DAY, 9, 12)  # Wednesday 9-12
		with self._now(at(18)):
			with self.assertRaises(frappe.ValidationError):
				api.request_missed_punch(str(DAY), "2026-10-07 11:00:00", "2026-10-07 15:00:00", "overlaps")

	def test_settings_defaults_patch_fills_only_unset_fields(self):
		from metactical.patches.time_tracker_settings_defaults import execute

		frappe.set_user("Administrator")
		frappe.db.sql(
			"delete from `tabSingles` where doctype='Time Tracker Settings' and field in "
			"('early_clockin_minutes','enforce_shift_window','backdate_limit_days','standard_day_hours')"
		)
		frappe.db.set_single_value("Time Tracker Settings", "max_shift_hours", 12)  # already chosen: must survive
		execute()
		get = lambda f: frappe.db.get_single_value("Time Tracker Settings", f)
		self.assertEqual((int(get("early_clockin_minutes")), int(get("enforce_shift_window")), int(get("backdate_limit_days"))), (15, 1, 14))
		self.assertEqual(float(get("max_shift_hours")), 12.0)
		self.assertEqual(float(get("standard_day_hours")), 8.0)
		frappe.db.set_single_value("Time Tracker Settings", "max_shift_hours", 16)
		frappe.clear_cache()

	# ---- Time Approval role ------------------------------------------------------------------

	def _approver_user(self):
		from metactical.patches.create_time_approval_role import execute

		frappe.set_user("Administrator")
		execute()
		email = "tc.timeapproval@example.com"
		if not frappe.db.exists("User", email):
			frappe.get_doc({"doctype": "User", "email": email, "first_name": "Role Holder", "send_welcome_email": 0}).insert(
				ignore_permissions=True
			)
		frappe.get_doc("User", email).add_roles("Time Approval")
		return email

	def test_time_approval_role_exists_and_is_idempotent(self):
		from metactical.patches.create_time_approval_role import execute

		execute()
		execute()
		self.assertEqual(frappe.db.count("Role", {"name": "Time Approval"}), 1)

	def test_every_instant_sent_to_the_browser_carries_its_offset(self):
		import re

		has_offset = re.compile(r"[+-]\d{2}:\d{2}$")
		self.clock("clock_in", at(9, 0))
		s = self.state(at(10, 0))
		for value in (s["server_now"], s["shift"]["start"], s["shift"]["end"], s["open_log"]["from_time"]):
			self.assertRegex(value, has_offset)
		self.assertRegex(s["today"]["logs"][0]["from_time"], has_offset)

	def test_times_typed_in_another_zone_are_stored_in_server_time(self):
		server = core.server_tz_name()
		# 13:00 UTC on 7 Oct is 09:00 in an Eastern server, whatever zone this site really uses
		expected = core.to_server_naive("2026-10-07 13:00:00", "UTC")
		if server in ("America/Toronto", "America/New_York"):
			self.assertEqual(expected, dt.datetime(2026, 10, 7, 9, 0))
		self.assertEqual(core.to_server_naive("2026-10-07 09:00:00", server), dt.datetime(2026, 10, 7, 9, 0))
		self.assertEqual(core.to_server_naive("2026-10-07 09:00:00"), dt.datetime(2026, 10, 7, 9, 0))
		with self.assertRaises(frappe.ValidationError):
			core.to_server_naive("2026-10-07 09:00:00", "Mars/Olympus")

	def test_request_made_in_utc_lands_at_the_right_server_time(self):
		log = self._closed_log()  # 09:00-17:00 server time
		out_utc = core.with_offset(at(17, 30))  # what the browser would get back for 17:30 server time
		frm = dt.datetime.fromisoformat(core.with_offset(at(8, 50))).astimezone(dt.timezone.utc)
		to = dt.datetime.fromisoformat(out_utc).astimezone(dt.timezone.utc)
		with self._now(at(18)):
			req = api.request_correction(
				log, frm.strftime("%Y-%m-%d %H:%M:%S"), to.strftime("%Y-%m-%d %H:%M:%S"), "Entered in UTC", timezone="UTC"
			)
		row = frappe.db.get_value("Checkin Request Modification", req["name"], ["requested_from", "requested_to"], as_dict=True)
		self.assertEqual((row.requested_from, row.requested_to), (at(8, 50), at(17, 30)))

	def test_display_zone_is_remembered_per_user(self):
		self.assertEqual(api.get_my_permissions()["display_zone"], "server")
		api.set_display_zone("America/Vancouver")
		self.assertEqual(api.get_my_permissions()["display_zone"], "America/Vancouver")
		api.set_display_zone("browser")
		self.assertEqual(api.get_my_permissions()["display_zone"], "browser")
		with self.assertRaises(frappe.ValidationError):
			api.set_display_zone("Pacific/Auckland")  # not on the list
		api.set_display_zone("server")
		self.assertEqual(api.get_my_permissions()["server_tz"], core.server_tz_name())

	# ---- schedules, roles, pay-cycle scope, patches ------------------------------------------

	def test_expected_hours_follow_the_schedule(self):
		D = frappe._dict
		settings = core.get_settings()
		self.assertEqual(core.expected_hours(D(start_time="09:00:00", end_time="17:00:00"), settings), 8)
		# the window may include lunch: Expected Hours says what is paid inside it
		self.assertEqual(core.expected_hours(D(start_time="10:00:00", end_time="19:00:00", tt_expected_hours=8), settings), 8)
		self.assertEqual(core.expected_hours(D(start_time="08:00:00", end_time="22:00:00"), settings), 14)  # a real 14h schedule
		# availability windows are not working days: deverp's Flex Shift and Store Shift
		self.assertEqual(core.expected_hours(D(start_time="00:01:00", end_time="23:59:59"), settings), settings.standard_day_hours)
		self.assertEqual(core.expected_hours(D(start_time="06:00:00", end_time="22:00:00"), settings), settings.standard_day_hours)

	def test_standard_shift_types_patch_is_idempotent(self):
		from metactical.patches.create_standard_shift_types import STANDARD, execute

		frappe.set_user("Administrator")
		execute()
		execute()
		for name, _start, _end, hours in STANDARD:
			self.assertEqual(float(frappe.db.get_value("Shift Type", name, "tt_expected_hours")), hours)

	def _legacy_request(self, day, status="Pending"):
		"""A request as the older page left them: made now, about an entry on `day`."""
		frappe.set_user("Administrator")
		name = frappe.get_doc(
			{"doctype": "Checkin Request Modification", "request_type": "Add", "user": USER, "date": str(day),
			 "status": status, "reason": "old", "requested_from": dt.datetime.combine(day, dt.time(9)),
			 "requested_to": dt.datetime.combine(day, dt.time(17)), "current_checkin": "-", "current_checkout": "-",
			 "requested_checkin": "9:00 AM", "requested_checkout": "5:00 PM"}
		).insert(ignore_permissions=True).name
		frappe.set_user(USER)
		return name

	def test_a_paid_out_period_cannot_be_changed_or_approved(self):
		frappe.set_user("Administrator")
		old = frappe.get_doc(
			{"doctype": "Clockin Log", "user": USER, "date": dt.date(2026, 9, 3), "from_time": dt.datetime(2026, 9, 3, 9),
			 "to_time": dt.datetime(2026, 9, 3, 17), "has_clocked_out": 1}
		).insert(ignore_permissions=True)
		frappe.set_user(USER)
		with self._now(at(18)):
			with self.assertRaises(frappe.ValidationError):
				api.request_correction(old.name, "2026-09-03 09:00:00", "2026-09-03 17:30:00", "too late for this")
			with self.assertRaises(frappe.ValidationError):
				api.request_missed_punch("2026-09-04", "2026-09-04 09:00:00", "2026-09-04 17:00:00", "too late for this")
		# a request made before the period closed cannot be approved afterwards
		stale = self._legacy_request(dt.date(2026, 9, 3))
		frappe.set_user(self._approver_user())
		with self._now(at(18)):
			with self.assertRaises(frappe.ValidationError):
				api.review_request(stale, "Approved")
			api.review_request(stale, "Declined", "closed")  # declining is still fine

	def test_patch_closes_only_entries_older_than_the_previous_cycle(self):
		from metactical.patches.close_stale_open_entries import execute

		frappe.set_user("Administrator")
		ancient = frappe.get_doc(
			{"doctype": "Clockin Log", "user": USER, "date": dt.date(2024, 2, 4), "from_time": dt.datetime(2024, 2, 4, 9)}
		).insert(ignore_permissions=True)
		with self._now(at(10)):
			execute()
		row = frappe.db.get_value("Clockin Log", ancient.name, ["has_clocked_out", "auto_closed", "total_hours", "from_time", "to_time"], as_dict=True)
		self.assertEqual((row.has_clocked_out, row.auto_closed, row.total_hours), (1, 1, 0))
		self.assertEqual(row.from_time, row.to_time)
		self.assertFalse(frappe.db.exists("Employee Checkin", {"employee": self.employee, "log_type": "OUT"}))  # no invented punch

		frappe.set_user(USER)
		self.clock("clock_in", at(9, 0))  # open today: must be left alone
		frappe.set_user("Administrator")
		with self._now(at(10)):
			execute()
		self.assertEqual(frappe.db.count("Clockin Log", {"user": USER, "has_clocked_out": 0}), 1)

	def test_region_patch_converts_text_and_clears_what_it_cannot_match(self):
		from metactical.patches.normalize_employee_regions import execute

		frappe.set_user("Administrator")
		frappe.db.set_value("Employee", self.employee, "ais_state", "British Columbia")
		execute()
		self.assertEqual(frappe.db.get_value("Employee", self.employee, "ais_state"), "CA-BC")
		frappe.db.set_value("Employee", self.employee, "ais_state", "Zorgonia")
		execute()
		self.assertFalse(frappe.db.get_value("Employee", self.employee, "ais_state"))
		self.assertTrue(frappe.db.exists("Comment", {"reference_doctype": "Employee", "reference_name": self.employee, "content": ["like", "%Zorgonia%"]}))

	# ---- approvals by pay cycle -------------------------------------------------------------------

	def test_role_holder_sees_every_request_in_the_cycle_and_can_decide(self):
		log = self._closed_log()
		with self._now(at(18)):
			change = api.request_correction(log, "2026-10-07 08:50:00", "2026-10-07 17:20:00", "Stayed late")["name"]
			add = api.request_missed_punch("2026-10-05", "2026-10-05 09:00:00", "2026-10-05 17:00:00", "Forgot to clock in")["name"]

		approver = self._approver_user()  # not the settings address, not an administrator: only the role
		frappe.set_user(approver)
		self.assertTrue(api.get_my_permissions()["can_review"])
		with self._now(at(18)):
			data = api.get_requests(0)
		rows = {r["name"]: r for r in data["rows"]}
		self.assertLessEqual({change, add}, set(rows))
		self.assertEqual(data["cycle"]["label"], "current")
		c = rows[change]
		self.assertEqual((c["request_type"], c["employee_name"]), ("Change", "Worker"))
		self.assertAlmostEqual(c["current_hours"], 8.0, places=3)
		self.assertAlmostEqual(c["delta_hours"], 0.5, places=2)
		self.assertTrue(c["same_day"][0]["is_this_entry"])
		a = rows[add]
		self.assertEqual((a["request_type"], a["current_hours"], a["same_day"]), ("Add", None, []))

		with self._now(at(18)):
			api.review_request(add, "Approved", "ok")
			api.review_request(change, "Declined", "Please attach a note")
			data = api.get_requests(0)
		by_name = {r["name"]: r for r in data["rows"]}
		self.assertEqual((by_name[add]["status"], by_name[change]["status"]), ("Approved", "Declined"))
		self.assertEqual(by_name[change]["review_comment"], "Please attach a note")
		self.assertEqual(by_name[change]["reviewed_by_name"], "Role Holder")
		self.assertGreaterEqual(data["counts"]["Approved"], 1)
		self.assertEqual(data["counts"]["All"], sum(data["counts"][k] for k in ("Pending", "Approved", "Declined")))

	def test_plain_employee_cannot_open_the_approvals_screen(self):
		self.assertFalse(api.get_my_permissions()["can_review"])
		for call in (lambda: api.get_requests(0), api.get_attention, api.expire_old_requests):
			with self.assertRaises(frappe.PermissionError):
				call()

	def test_hr_manager_alone_cannot_approve(self):
		frappe.set_user("Administrator")
		email = "tc.hrmanager@example.com"
		if not frappe.db.exists("User", email):
			frappe.get_doc({"doctype": "User", "email": email, "first_name": "Hr Only", "send_welcome_email": 0}).insert(
				ignore_permissions=True
			)
		frappe.get_doc("User", email).add_roles("HR Manager")
		frappe.set_user(email)
		self.assertFalse(api.get_my_permissions()["can_review"])
		for call in (lambda: api.get_requests(0), api.expire_old_requests):
			with self.assertRaises(frappe.PermissionError):
				call()

	def test_go_back_one_cycle_and_only_an_administrator_can_go_further(self):
		current = self._legacy_request(dt.date(2026, 10, 5))
		previous = self._legacy_request(dt.date(2026, 9, 25))
		paid = self._legacy_request(dt.date(2026, 9, 8))  # two cycles back: already paid out

		frappe.set_user(self._approver_user())  # Time Approval only
		with self._now(at(18)):
			cur = api.get_requests(0)
			prev = api.get_requests(1)
			self.assertEqual((cur["cycle"]["label"], cur["has_newer"], cur["has_older"]), ("current", False, True))
			self.assertEqual((prev["cycle"]["label"], prev["has_newer"], prev["has_older"]), ("previous", True, False))  # no further
			self.assertIn(current, {r["name"] for r in cur["rows"]})
			self.assertIn(previous, {r["name"] for r in prev["rows"]})
			self.assertNotIn(paid, {r["name"] for r in cur["rows"] + prev["rows"]})
			with self.assertRaises(frappe.PermissionError):
				api.get_requests(2)
			self.assertGreaterEqual(cur["hidden_older_pending"], 1)
			self.assertEqual(api.get_my_permissions()["pending_count"], cur["pending_count"])

		frappe.set_user("Administrator")
		with self._now(at(18)):
			old = api.get_requests(2)
		self.assertEqual((old["cycle"]["label"], old["has_older"], old["has_newer"]), ("older", False, True))  # nothing earlier exists
		self.assertIn(paid, {r["name"] for r in old["rows"]})
		self.assertTrue(old["can_browse_history"])

	def test_old_pending_requests_can_be_expired_in_one_go(self):
		current = self._legacy_request(dt.date(2026, 10, 5))
		paid = self._legacy_request(dt.date(2026, 9, 3))
		frappe.set_user(self._approver_user())
		with self._now(at(18)):
			result = api.expire_old_requests()
		self.assertGreaterEqual(result["expired"], 1)
		row = frappe.db.get_value("Checkin Request Modification", paid, ["status", "review_comment"], as_dict=True)
		self.assertEqual(row.status, "Declined")
		self.assertIn("Expired", row.review_comment)
		self.assertEqual(frappe.db.get_value("Checkin Request Modification", current, "status"), "Pending")

	# ---- Phase 2: the work day follows the employee's work zone ------------------------------

	def test_work_day_follows_the_work_zone(self):
		import pytz

		server = core.server_tz_name()
		start = at(1, 0)  # 01:00 server time
		pacific = pytz.timezone(server).localize(start).astimezone(pytz.timezone("America/Vancouver")).date()
		self.assertEqual(core.work_day(start, "America/Vancouver"), pacific)
		self.assertEqual(core.work_day(start, server), start.date())
		self.assertEqual(core.work_day(start, None), start.date())

	def test_employee_region_sets_the_work_zone(self):
		try:
			for region, tz in (("CA-ON", "America/Toronto"), ("CA-AB", "America/Edmonton"), ("US-TX", "America/Vancouver"),
							   ("OTHER", "America/Vancouver"), ("", core.server_tz_name())):
				frappe.db.set_value("Employee", self.employee, "ais_state", region)
				with self._now(at(10)):
					state = api.get_state()
				self.assertEqual(state["work"]["tz"], tz, region)
		finally:
			frappe.db.set_value("Employee", self.employee, "ais_state", "")

	def test_a_missed_day_lands_on_the_work_day_not_the_server_day(self):
		frappe.db.set_value("Employee", self.employee, "ais_state", "OTHER")  # Pacific work days
		try:
			server_start, server_end = at(1, 0), at(9, 0)  # the early hours on the server clock
			work_day = core.work_day(server_start, "America/Vancouver")
			with self._now(at(12)):
				req = api.request_missed_punch(str(work_day), str(server_start), str(server_end), "Worked the early shift")
			frappe.set_user(self._approver_user())
			with self._now(at(12)):
				api.review_request(req["name"], "Approved")
			self.assertEqual(frappe.db.get_value("Clockin Log", {"user": USER, "from_time": server_start}, "date"), work_day)
		finally:
			frappe.db.set_value("Employee", self.employee, "ais_state", "")

	def test_missed_day_defaults_put_the_shift_on_that_work_day(self):
		frappe.db.set_value("Employee", self.employee, "ais_state", "OTHER")
		try:
			with self._now(at(12)):
				d = api.get_missed_defaults(str(DAY))
			start = dt.datetime.fromisoformat(d["from_time"]).replace(tzinfo=None)
			self.assertEqual(core.work_day(start, "America/Vancouver"), DAY)
		finally:
			frappe.db.set_value("Employee", self.employee, "ais_state", "")

	# ---- forgot to clock out ---------------------------------------------------------------

	def test_reminder_link_tokens_are_signed_and_expire(self):
		from metactical.time_tracker import reminders

		token = reminders.make_token("LOG-1")
		self.assertEqual(reminders.read_token(token), "LOG-1")
		for bad in (token[:-3] + "abc", "garbage", "", reminders.make_token("LOG-1", valid_hours=-1)):
			with self.assertRaises(reminders.InvalidLink):
				reminders.read_token(bad)

	def test_forgotten_clock_out_is_reminded_once_then_closed_at_the_shift_end(self):
		from metactical.time_tracker import reminders

		self.clock("clock_in", at(9, 0))
		sent = []
		fake = lambda user, subject, html, sms: sent.append(subject) or ["email"]
		with patch.object(reminders, "send", side_effect=fake):
			with self._now(at(17, 5)):
				reminders.run(user=USER)  # only 5 minutes past the end: too early
			self.assertEqual(sent, [])
			with self._now(at(17, 20)):
				reminders.run(user=USER)
			self.assertEqual(len(sent), 1)
			with self._now(at(17, 40)):
				reminders.run(user=USER)
			self.assertEqual(len(sent), 1)  # never twice
			with self._now(at(21, 10)):
				reminders.run(user=USER)  # more than 2 hours past the end
		row = frappe.db.get_value("Clockin Log", {"user": USER}, ["has_clocked_out", "auto_closed", "closed_via", "to_time", "total_hours"], as_dict=True)
		self.assertEqual((row.has_clocked_out, row.auto_closed, row.closed_via), (1, 1, "auto"))
		self.assertEqual(row.to_time, at(17, 0))  # at the scheduled end, not when the job ran
		self.assertAlmostEqual(row.total_hours, 8.0, places=3)
		self.assertEqual(len(sent), 2)  # the reminder, then the "we closed it" notice
		self.assertTrue(frappe.db.exists("Employee Checkin", {"employee": self.employee, "log_type": "OUT"}))

	def test_an_idle_run_does_no_work(self):
		from metactical.time_tracker import reminders

		def idle_run(when):
			# the job must not look up shifts or employees, let alone send anything, when nothing is due
			with patch.object(core, "expected_end_for", side_effect=AssertionError("must not run")), patch.object(
				reminders, "send", side_effect=AssertionError("must not send")
			):
				with self._now(when):
					reminders.run(user=USER)

		idle_run(at(23, 0))  # nobody is clocked in
		self.clock("clock_in", at(9, 0))
		idle_run(at(12, 0))  # open, but nothing is due until 17:15

	def test_the_follow_up_time_is_set_once_and_moves_on(self):
		from metactical.time_tracker import reminders

		self.clock("clock_in", at(9, 0))
		name = frappe.db.get_value("Clockin Log", {"user": USER}, "name")
		due = lambda: frappe.db.get_value("Clockin Log", name, "followup_due_on")
		self.assertEqual(due(), at(17, 15))  # scheduled end 17:00 + 15 minutes
		with patch.object(reminders, "send", return_value=["email"]):
			with self._now(at(17, 20)):
				reminders.run(user=USER)
			self.assertEqual(due(), at(19, 0))  # next: the auto-close, 2 hours past the end
			with self._now(at(21, 5)):
				reminders.run(user=USER)
		self.assertIsNone(due())  # closed: nothing left to follow up


	def test_reminders_and_auto_close_can_be_switched_off(self):
		from metactical.time_tracker import reminders

		self.clock("clock_in", at(9, 0))
		frappe.set_user("Administrator")
		frappe.db.set_single_value("Time Tracker Settings", "reminder_minutes_after_shift_end", 0)
		frappe.db.set_single_value("Time Tracker Settings", "auto_close_hours_after_shift_end", 0)
		frappe.clear_cache(doctype="Time Tracker Settings")
		try:
			with patch.object(reminders, "send", side_effect=AssertionError("must not send")):
				with self._now(at(23, 0)):
					reminders.run(user=USER)
			self.assertEqual(frappe.db.count("Clockin Log", {"user": USER, "has_clocked_out": 0}), 1)
		finally:
			frappe.db.set_single_value("Time Tracker Settings", "reminder_minutes_after_shift_end", 15)
			frappe.db.set_single_value("Time Tracker Settings", "auto_close_hours_after_shift_end", 2)
			frappe.clear_cache(doctype="Time Tracker Settings")

	def test_the_link_clocks_out_now_exactly_once_and_only_that_entry(self):
		from metactical.time_tracker import reminders

		self.clock("clock_in", at(9, 0))
		name = frappe.db.get_value("Clockin Log", {"user": USER, "has_clocked_out": 0}, "name")
		token = reminders.make_token(name)
		frappe.set_user("Guest")
		self.assertTrue(api.get_clockout_link(token)["open"])
		with self._now(at(17, 30)):
			done = api.confirm_clockout(token)
		self.assertFalse(done["open"])
		to_time = frappe.db.get_value("Clockin Log", name, "to_time")
		self.assertEqual(to_time, at(17, 30))  # the moment of the click
		self.assertEqual(frappe.db.get_value("Clockin Log", name, "closed_via"), "link")
		with self._now(at(18, 30)):
			api.confirm_clockout(token)  # pressing again changes nothing
		self.assertEqual(frappe.db.get_value("Clockin Log", name, "to_time"), to_time)
		with self.assertRaises(reminders.InvalidLink):
			api.confirm_clockout("not-a-token")

	def test_the_approver_sees_forgotten_entries_and_can_close_or_confirm_them(self):
		from metactical.time_tracker import reminders

		self.clock("clock_in", at(9, 0))  # never clocked out
		frappe.set_user(self._approver_user())
		with self._now(at(16, 0)):
			self.assertEqual([r for r in api.get_attention()["open"] if r["employee_name"] == "Worker"], [])  # still inside the shift
		with self._now(at(19, 0)):
			mine = [r for r in api.get_attention()["open"] if r["employee_name"] == "Worker"]
			self.assertEqual(len(mine), 1)
			with self.assertRaises(frappe.ValidationError):
				api.close_entry(mine[0]["name"], "2026-10-07 08:00:00")  # before they clocked in
			api.close_entry(mine[0]["name"], "2026-10-07 17:10:00")
		row = frappe.db.get_value("Clockin Log", mine[0]["name"], ["to_time", "closed_via", "closed_by"], as_dict=True)
		self.assertEqual((row.to_time, row.closed_via), (at(17, 10), "approver"))

		# something the system closed: the approver confirms it
		frappe.set_user("Administrator")
		log = frappe.get_doc({"doctype": "Clockin Log", "user": USER, "date": DAY, "from_time": at(18, 0), "to_time": at(19, 0),
							  "has_clocked_out": 1, "auto_closed": 1, "closed_via": "auto"}).insert(ignore_permissions=True)
		frappe.set_user(self._approver_user())
		with self._now(at(20, 0)):
			self.assertIn(log.name, [r["name"] for r in api.get_attention()["auto_closed"]])
			api.close_entry(log.name)  # "looks right"
			self.assertNotIn(log.name, [r["name"] for r in api.get_attention()["auto_closed"]])

	# ---- Rocket.Chat, and the build number ---------------------------------------------------

	def _forgotten(self):
		self.clock("clock_in", at(9, 0))
		return frappe.db.get_value("Clockin Log", {"user": USER}, "name")

	def test_auto_close_posts_name_link_scheduled_and_closed_time_to_rocketchat(self):
		from metactical.time_tracker import reminders

		name = self._forgotten()
		posts = []
		fake_post = lambda url, json=None, timeout=None: posts.append((url, json)) or SimpleNamespace(raise_for_status=lambda: None)
		with patch.object(reminders, "send", return_value=["email"]), patch.object(
			reminders, "_rocketchat_settings", return_value=("http://rc.test/hooks/abc", "Payroll-Time-Adjustments")
		), patch.object(reminders.requests, "post", side_effect=fake_post):
			with self._now(at(19, 5)):  # 2 hours + 5 minutes past the 17:00 end
				reminders.run(user=USER)
		self.assertEqual(len(posts), 1)
		url, body = posts[0]
		self.assertEqual((url, body["channel"]), ("http://rc.test/hooks/abc", "#Payroll-Time-Adjustments"))
		for needle in ("Worker", f"/app/clockin-log/{name}", "Scheduled time", "05:00 PM", "Auto-closed time", "07:05 PM"):
			self.assertIn(needle, body["text"])
		self.assertEqual(frappe.db.get_value("Clockin Log", name, "to_time"), at(17, 0))

	def test_without_a_webhook_nothing_is_posted(self):
		from metactical.time_tracker import reminders

		self._forgotten()
		with patch.object(reminders, "send", return_value=["email"]), patch.object(
			reminders, "_rocketchat_settings", return_value=(None, "Payroll-Time-Adjustments")
		), patch.object(reminders.requests, "post", side_effect=AssertionError("must not post")):
			with self._now(at(19, 5)):
				reminders.run(user=USER)
		self.assertEqual(frappe.db.count("Clockin Log", {"user": USER, "has_clocked_out": 0}), 0)  # still closed

	def test_a_failing_rocketchat_never_blocks_the_close(self):
		from metactical.time_tracker import reminders

		name = self._forgotten()
		with patch.object(reminders, "send", return_value=["email"]), patch.object(
			reminders, "_rocketchat_settings", return_value=("http://rc.test/hooks/abc", "Payroll-Time-Adjustments")
		), patch.object(reminders.requests, "post", side_effect=ConnectionError("down")):
			with self._now(at(19, 5)):
				reminders.run(user=USER)
		self.assertEqual(frappe.db.get_value("Clockin Log", name, ["has_clocked_out", "auto_closed"], as_dict=True), {"has_clocked_out": 1, "auto_closed": 1})

	def test_the_build_number_is_reported(self):
		from metactical.time_tracker.build import BUILD

		self.assertEqual(api.get_my_permissions()["build"], BUILD)
		self.assertIsInstance(BUILD, int)


class TestLocations(FrappeTestCase):
	def test_free_text_becomes_iso_codes(self):
		from metactical.time_tracker import locations as L

		cases = {"BC": "CA-BC", "British Columbia": "CA-BC", "B.C.": "CA-BC", "bc ": "CA-BC", "Ontario": "CA-ON",
				 "ON": "CA-ON", "Quebec": "CA-QC", "Texas": "US-TX", "tx": "US-TX", "CA-AB": "CA-AB", "us-wa": "US-WA",
				 "California": "US-CA", "Other": "OTHER"}
		for text, code in cases.items():
			self.assertEqual(L.normalize_region(text), code, text)
		for text in ("Zorgonia", "", None, "Manila"):
			self.assertIsNone(L.normalize_region(text))

	def test_every_option_is_valid_and_canada_has_a_zone(self):
		from metactical.time_tracker import locations as L

		self.assertEqual(len(L.CODES), 13 + 51 + 1)  # provinces and territories, 50 states + DC, OTHER
		self.assertEqual(len(set(L.CODES)), len(L.CODES))
		for code in L.CODES:
			self.assertEqual(L.normalize_region(code), code)
		self.assertEqual(set(L.CANADA_ZONE), {c for c in L.CODES if c.startswith("CA-")})

	def test_time_zone_rule_canada_by_province_everyone_else_pacific(self):
		from metactical.time_tracker import locations as L

		self.assertEqual(L.work_time_zone("CA-ON"), "America/Toronto")
		self.assertEqual(L.work_time_zone("CA-AB"), "America/Edmonton")
		self.assertEqual(L.work_time_zone("CA-SK"), "America/Regina")
		self.assertEqual(L.work_time_zone("US-TX"), "America/Vancouver")  # outside Canada: Pacific
		self.assertEqual(L.work_time_zone("OTHER"), "America/Vancouver")
		self.assertEqual(L.work_time_zone(None, default="SERVER"), "SERVER")  # unknown: the server zone
		self.assertEqual((L.country_of("CA-BC"), L.country_of("US-TX"), L.country_of("OTHER")), ("CA", "US", None))
