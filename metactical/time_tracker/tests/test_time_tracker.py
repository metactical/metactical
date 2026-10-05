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
		sa = frappe.get_doc(
			{"doctype": "Shift Assignment", "employee": cls.employee, "shift_type": "TC Day",
			 "company": cls.company, "start_date": "2026-01-01", "status": "Active"}
		).insert(ignore_permissions=True)
		sa.submit()
		s = frappe.get_doc("Time Tracker Settings")
		s.checkin_approver = APPROVER
		s.start_date = "2026-10-01"
		s.set("pay_cycles", [{"from_date": "2026-10-01", "to_date": "2026-10-14"}])
		s.early_clockin_minutes = 15
		s.enforce_shift_window = 1
		s.max_shift_hours = 16
		s.save(ignore_permissions=True)
		frappe.clear_cache()

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
		self.assertEqual(s["open_log"]["from_time"][:16], "2026-10-07 09:02")
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
		with self.assertRaises(frappe.ValidationError):
			api.request_correction(log, "2026-10-07 09:00:00", "2026-10-07 17:00:00", "")
		with self.assertRaises(frappe.ValidationError):
			api.request_correction(log, "2026-10-07 17:00:00", "2026-10-07 09:00:00", "swapped")

	def test_only_the_approver_can_approve_and_never_their_own(self):
		log = self._closed_log()
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
