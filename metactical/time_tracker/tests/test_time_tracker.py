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
		s.start_date = "2026-10-01"
		s.set("pay_cycles", [{"from_date": "2026-10-01", "to_date": "2026-10-14"}])
		s.early_clockin_minutes = 15
		s.enforce_shift_window = 1
		s.max_shift_hours = 16
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
					  "enforce_shift_window", "max_shift_hours", "backdate_limit_days"):
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
		self.assertEqual(cycle["shift_hours"], 8.0)
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
			"('early_clockin_minutes','enforce_shift_window','backdate_limit_days')"
		)
		frappe.db.set_single_value("Time Tracker Settings", "max_shift_hours", 12)  # already chosen: must survive
		execute()
		get = lambda f: frappe.db.get_single_value("Time Tracker Settings", f)
		self.assertEqual((int(get("early_clockin_minutes")), int(get("enforce_shift_window")), int(get("backdate_limit_days"))), (15, 1, 14))
		self.assertEqual(float(get("max_shift_hours")), 12.0)
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

	def test_role_holder_sees_every_request_and_can_decide(self):
		log = self._closed_log()
		base_pending = frappe.db.count("Checkin Request Modification", {"status": "Pending"})
		base_decided = frappe.db.count("Checkin Request Modification", {"status": ["in", ["Approved", "Declined"]]})
		with self._now(at(18)):
			change = api.request_correction(log, "2026-10-07 08:50:00", "2026-10-07 17:20:00", "Stayed late")["name"]
			add = api.request_missed_punch("2026-10-05", "2026-10-05 09:00:00", "2026-10-05 17:00:00", "Forgot to clock in")["name"]

		approver = self._approver_user()  # not the settings address, not HR Manager: only the role
		frappe.set_user(approver)
		self.assertTrue(api.get_my_permissions()["can_review"])
		with self._now(at(18)):
			data = api.get_requests("Pending")
		self.assertEqual(data["pending_count"], base_pending + 2)
		rows = {r["name"]: r for r in data["rows"]}
		self.assertLessEqual({change, add}, set(rows))  # the screen shows everyone's requests, not just these

		c = rows[change]
		self.assertEqual(c["request_type"], "Change")
		self.assertEqual(c["employee_name"], "Worker")
		self.assertAlmostEqual(c["current_hours"], 8.0, places=3)
		self.assertAlmostEqual(c["requested_hours"], 8.5 + 1 / 6 - 1 / 6, places=2)  # 08:50-17:20 = 8h30
		self.assertAlmostEqual(c["delta_hours"], 0.5, places=2)
		self.assertEqual(len(c["same_day"]), 1)
		self.assertTrue(c["same_day"][0]["is_this_entry"])
		a = rows[add]
		self.assertEqual((a["request_type"], a["current_hours"], a["same_day"]), ("Add", None, []))
		self.assertAlmostEqual(a["requested_hours"], 8.0, places=3)

		with self._now(at(18)):
			api.review_request(add, "Approved", "ok")
			api.review_request(change, "Declined", "Please attach a note")
		with self._now(at(18)):
			done = api.get_requests("Decided")
		self.assertEqual((done["pending_count"], done["decided_count"]), (base_pending, base_decided + 2))
		by_name = {r["name"]: r for r in done["rows"]}
		self.assertEqual(by_name[change]["status"], "Declined")
		self.assertEqual(by_name[change]["review_comment"], "Please attach a note")
		self.assertEqual(by_name[change]["reviewed_by_name"], "Role Holder")

	def test_plain_employee_cannot_open_the_approvals_screen(self):
		self.assertFalse(api.get_my_permissions()["can_review"])
		with self.assertRaises(frappe.PermissionError):
			api.get_requests("Pending")

	# ---- time zones (display only: stored times stay in server time) -------------------------

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
