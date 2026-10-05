"""Time tracker rules: who the user is, which shift applies, what the clock may do.

Everything here uses server time. The browser never sends a timestamp.
"""

import datetime as dt

import frappe
from frappe import _
from frappe.utils import add_days, flt, get_datetime, getdate, now_datetime

SETTINGS = "Time Tracker Settings"


class Blocked(Exception):
	"""The user can see the tracker but cannot clock yet. Carries a stable code for the UI."""

	def __init__(self, code, message):
		super().__init__(message)
		self.code = code
		self.message = message


# ---- settings -----------------------------------------------------------------------------


def get_settings():
	s = frappe.get_cached_doc(SETTINGS)
	return frappe._dict(
		approver=(s.checkin_approver or "").strip(),
		logout_delay=int(s.logout_delay or 0),
		early_minutes=int(s.get("early_clockin_minutes") if s.get("early_clockin_minutes") is not None else 15),
		enforce_window=int(s.get("enforce_shift_window") if s.get("enforce_shift_window") is not None else 1),
		max_shift_hours=flt(s.get("max_shift_hours")) or 16.0,
		pay_cycles=[(getdate(r.from_date), getdate(r.to_date)) for r in (s.pay_cycles or [])],
	)


# ---- time helpers -------------------------------------------------------------------------


def to_timedelta(v):
	"""Frappe hands Time values back as timedelta, time or str depending on the call."""
	if v is None or v == "":
		return dt.timedelta(0)
	if isinstance(v, dt.timedelta):
		return v
	if isinstance(v, dt.time):
		return dt.timedelta(hours=v.hour, minutes=v.minute, seconds=v.second)
	h, m, *rest = [int(float(p)) for p in str(v).split(":")]
	return dt.timedelta(hours=h, minutes=m, seconds=rest[0] if rest else 0)


def hours_between(start, end):
	"""Signed hours. A negative result is a data problem, never silently flipped positive."""
	return (get_datetime(end) - get_datetime(start)).total_seconds() / 3600.0


def shift_occurrence(shift, day):
	"""(start, end) datetimes of the shift that begins on `day`. Handles shifts that cross midnight."""
	midnight = dt.datetime.combine(getdate(day), dt.time())
	start = midnight + to_timedelta(shift.start_time)
	end = midnight + to_timedelta(shift.end_time)
	if end <= start:
		end += dt.timedelta(days=1)
	return start, end


def shift_window(shift, now, early_minutes):
	"""Where `now` sits relative to the shift.

	Returns (state, start, end). state is "open" (clocking is allowed), "before" (next shift is
	later) or "after" (today's shift is over).
	"""
	grace = dt.timedelta(minutes=early_minutes)
	today = now.date()
	for day in (add_days(today, -1), today, add_days(today, 1)):
		start, end = shift_occurrence(shift, day)
		if start - grace <= now <= end:
			return "open", start, end
	start, end = shift_occurrence(shift, today)
	if now < start - grace:
		return "before", start, end
	nxt_start, nxt_end = shift_occurrence(shift, add_days(today, 1))
	return "after", nxt_start, nxt_end


# ---- who / which shift ---------------------------------------------------------------------


def get_employee(user):
	row = frappe.db.get_value(
		"Employee",
		{"user_id": user, "status": "Active"},
		["name", "employee_name", "default_shift", "company"],
		as_dict=True,
	)
	if not row:
		raise Blocked(
			"no_employee",
			_("Your user is not linked to an active Employee record. Ask HR to link {0} to an Employee.").format(user),
		)
	return row


def get_shift(employee, on_date):
	"""Active, submitted Shift Assignment covering the date, falling back to the Employee's default shift."""
	assignment = frappe.db.sql(
		"""select shift_type from `tabShift Assignment`
		where employee=%(emp)s and docstatus=1 and status='Active'
			and start_date <= %(d)s and (end_date is null or end_date >= %(d)s)
		order by start_date desc limit 1""",
		{"emp": employee.name, "d": on_date},
	)
	shift_name = assignment[0][0] if assignment else employee.default_shift
	if not shift_name:
		raise Blocked(
			"no_shift",
			_("{0} has no active Shift Assignment. Ask HR to assign a shift.").format(employee.employee_name),
		)
	return frappe.db.get_value("Shift Type", shift_name, ["name", "start_time", "end_time"], as_dict=True)


def get_cycle(on_date, settings=None):
	settings = settings or get_settings()
	d = getdate(on_date)
	for start, end in settings.pay_cycles:
		if start <= d <= end:
			return start, end
	raise Blocked("no_cycle", _("No pay cycle covers {0}. Ask HR to add one in Time Tracker Settings.").format(d))


def context(user=None):
	"""Resolve user -> employee -> shift. Raises Blocked with a UI-safe reason."""
	user = user or frappe.session.user
	if user == "Guest":
		raise Blocked("not_logged_in", _("Please log in."))
	settings = get_settings()
	employee = get_employee(user)
	now = now_datetime()
	shift = get_shift(employee, now.date())
	return frappe._dict(user=user, employee=employee, shift=shift, settings=settings, now=now)


# ---- logs ---------------------------------------------------------------------------------

LOG_FIELDS = ["name", "date", "from_time", "to_time", "total_hours", "has_clocked_out"]


def open_logs(user):
	return frappe.get_all(
		"Clockin Log",
		filters={"user": user, "has_clocked_out": 0},
		fields=LOG_FIELDS,
		order_by="from_time desc",
	)


def logs_for_day(user, day):
	return frappe.get_all(
		"Clockin Log",
		filters={"user": user, "date": getdate(day)},
		fields=LOG_FIELDS,
		order_by="from_time asc",
	)


def log_hours(log, now):
	"""Hours for one log. An open log counts up to `now`."""
	if log.has_clocked_out and log.to_time:
		return max(0.0, hours_between(log.from_time, log.to_time))
	return max(0.0, hours_between(log.from_time, now))


def serialize_log(log, now):
	return {
		"name": log.name,
		"date": str(log.date),
		"from_time": str(log.from_time),
		"to_time": str(log.to_time) if log.to_time else None,
		"hours": round(log_hours(log, now), 4),
		"open": not log.has_clocked_out,
	}


def day_totals(user, start, end, now):
	"""{date: (hours, log_count)} for every date in the range, zero-filled."""
	rows = frappe.get_all(
		"Clockin Log",
		filters={"user": user, "date": ["between", [start, end]]},
		fields=LOG_FIELDS,
	)
	out = {}
	d = getdate(start)
	while d <= getdate(end):
		out[d] = [0.0, 0]
		d = add_days(d, 1)
	for r in rows:
		cell = out.setdefault(getdate(r.date), [0.0, 0])
		cell[0] += log_hours(r, now)
		cell[1] += 1
	return out


def lock_employee(employee_name):
	"""Serialise clock actions per employee so a double tap cannot create two open logs."""
	frappe.db.sql("select name from `tabEmployee` where name=%s for update", employee_name)
