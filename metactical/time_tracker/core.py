"""Time tracker rules: who the user is, which shift applies, what the clock may do.

Everything here uses server time. The browser never sends a timestamp.
"""

import datetime as dt

import frappe
import pytz
from frappe import _
from frappe.utils import add_days, flt, get_datetime, getdate, now_datetime

from metactical.time_tracker import locations

SETTINGS = "Time Tracker Settings"

# A day is only "short" when it misses the shift by more than this.
SHORT_DAY_TOLERANCE_HOURS = 0.25


class Blocked(Exception):
	"""The user can see the tracker but cannot clock yet. Carries a stable code for the UI."""

	def __init__(self, code, message):
		super().__init__(message)
		self.code = code
		self.message = message


# ---- time zones ---------------------------------------------------------------------------
#
# Everything is stored and calculated in the SITE time zone ("server time"). The screens may display it in
# another zone, so every instant sent to the browser carries its UTC offset.


def server_tz_name():
	return frappe.utils.get_system_timezone() or "UTC"


def _zone(name=None):
	try:
		return pytz.timezone(name or server_tz_name())
	except pytz.UnknownTimeZoneError:
		frappe.throw(_("Unknown time zone: {0}").format(name))


def with_offset(value):
	"""Server-time value -> ISO string with its UTC offset, e.g. 2026-10-05T16:18:00-04:00 (None stays None)."""
	if value in (None, ""):
		return None
	d = get_datetime(value).replace(microsecond=0)
	if d.tzinfo is None:
		d = _zone().localize(d, is_dst=False)
	return d.isoformat()


def to_server_naive(value, tz_name=None):
	"""A time the user typed in `tz_name` (None = server time) -> naive datetime in server time."""
	d = get_datetime(value)
	if d.tzinfo is not None:
		return d.astimezone(_zone()).replace(tzinfo=None)
	if not tz_name or tz_name == server_tz_name():
		return d
	return _zone(tz_name).localize(d, is_dst=False).astimezone(_zone()).replace(tzinfo=None)


# Zones a user can pick for DISPLAY, besides "server" and "browser" (this computer's zone).
DISPLAY_ZONES = (
	"America/Vancouver",  # Pacific
	"America/Edmonton",  # Mountain
	"America/Winnipeg",  # Central
	"America/Toronto",  # Eastern
	"America/Halifax",  # Atlantic
	"UTC",
)
ZONE_DEFAULT_KEY = "time_clock_display_zone"


def get_display_zone(user=None):
	v = frappe.defaults.get_user_default(ZONE_DEFAULT_KEY, user=user or frappe.session.user)
	return v if v in ("server", "browser") or v in DISPLAY_ZONES else "server"


def work_day(value, tz_name):
	"""The calendar day a server-time moment falls on in `tz_name` (the employee's work zone)."""
	d = get_datetime(value)
	if not tz_name or tz_name == server_tz_name():
		return d.date()
	return _zone().localize(d, is_dst=False).astimezone(_zone(tz_name)).date()


def shift_times_for_workday(shift, workday, tz_name):
	"""(start, end) in server time of the shift that belongs to work day `workday` in `tz_name`.

	Shifts are written in server time. For someone whose work zone is far from it, the shift that is their
	Tuesday may begin on the server's Monday, so look a day either side.
	"""
	workday = getdate(workday)
	for offset in (0, -1, 1):
		start, end = shift_occurrence(shift, add_days(workday, offset))
		if work_day(start, tz_name) == workday:
			return start, end
	return shift_occurrence(shift, workday)


# ---- settings -----------------------------------------------------------------------------


def get_settings():
	s = frappe.get_cached_doc(SETTINGS)
	return frappe._dict(
		approver=(s.checkin_approver or "").strip(),
		logout_delay=int(s.logout_delay or 0),
		early_minutes=int(s.get("early_clockin_minutes") if s.get("early_clockin_minutes") is not None else 15),
		enforce_window=int(s.get("enforce_shift_window") if s.get("enforce_shift_window") is not None else 1),
		max_shift_hours=flt(s.get("max_shift_hours")) or 16.0,
		backdate_days=int(s.get("backdate_limit_days") if s.get("backdate_limit_days") is not None else 14),
		standard_day_hours=flt(s.get("standard_day_hours")) or 8.0,
		reminder_minutes=int(s.get("reminder_minutes_after_shift_end") if s.get("reminder_minutes_after_shift_end") is not None else 15),
		auto_close_hours=int(s.get("auto_close_hours_after_shift_end") if s.get("auto_close_hours_after_shift_end") is not None else 2),
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


def employee_for_user(user):
	"""The active Employee row for a user (with its work time zone), or None."""
	fields = ["name", "employee_name", "default_shift", "company"]
	has_region = frappe.get_meta("Employee").has_field("ais_state")
	if has_region:
		fields.append("ais_state")
	row = frappe.db.get_value("Employee", {"user_id": user, "status": "Active"}, fields, as_dict=True)
	if row:
		row["ais_state"] = row.get("ais_state") if has_region else None
		row["work_tz"] = locations.work_time_zone(row["ais_state"], default=server_tz_name())
	return row


def work_zone_of_user(user):
	row = employee_for_user(user)
	return row.work_tz if row else server_tz_name()


def get_employee(user):
	row = employee_for_user(user)
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
	fields = ["name", "start_time", "end_time"]
	if frappe.get_meta("Shift Type").has_field("tt_expected_hours"):
		fields.append("tt_expected_hours")
	return frappe.db.get_value("Shift Type", shift_name, fields, as_dict=True)


# A shift longer than this is an availability window (Flex Shift 00:01-23:59, Store Shift 06:00-22:00), not a
# working day. Some people do work 12-14 hours, so anything up to 14 hours counts as a real schedule.
MAX_SCHEDULED_SHIFT_HOURS = 14


def expected_hours(shift, settings=None):
	"""Paid hours a normal day is expected to be on this schedule.

	Order: the shift's own Expected Hours; else the shift's length when it is a real schedule (up to 14
	hours); else the Standard Day Hours setting (8 by default).
	"""
	settings = settings or get_settings()
	own = flt(shift.get("tt_expected_hours")) if hasattr(shift, "get") else flt(getattr(shift, "tt_expected_hours", 0))
	if own > 0:
		return own
	start, end = shift_occurrence(shift, dt.date(2000, 1, 3))
	length = hours_between(start, end)
	if 0 < length <= MAX_SCHEDULED_SHIFT_HOURS:
		return length
	return settings.standard_day_hours


def expected_end(shift, from_time, settings=None):
	"""When an entry that started at `from_time` is expected to end: the scheduled end of the shift it belongs
	to, else `expected hours` after it started."""
	settings = settings or get_settings()
	f = get_datetime(from_time)
	for offset in (0, -1, 1):
		start, end = shift_occurrence(shift, add_days(f.date(), offset))
		if start - dt.timedelta(hours=2) <= f <= end:
			return end
	return f + dt.timedelta(hours=expected_hours(shift, settings))


def expected_end_for(user, from_time, settings=None):
	"""expected_end() for a user's entry, or None when they have no employee/shift to measure against."""
	row = employee_for_user(user)
	if not row:
		return None
	try:
		shift = get_shift(row, getdate(from_time))
	except Blocked:
		return None
	return expected_end(shift, from_time, settings)


def get_cycle(on_date, settings=None):
	settings = settings or get_settings()
	d = getdate(on_date)
	for start, end in settings.pay_cycles:
		if start <= d <= end:
			return start, end
	raise Blocked("no_cycle", _("No pay cycle covers {0}. Ask HR to add one in Time Tracker Settings.").format(d))


def today():
	return now_datetime().date()


def scope_cycles(on_date, settings=None):
	"""The current and the previous pay cycle: the only periods that can still be changed or approved.
	Older ones are paid out. None when no cycle covers `on_date`."""
	settings = settings or get_settings()
	d = getdate(on_date)
	cycles = sorted(settings.pay_cycles, key=lambda c: c[0])
	for i, (start, end) in enumerate(cycles):
		if start <= d <= end:
			prev = cycles[i - 1] if i > 0 else None
			return {
				"current_from": start,
				"current_to": end,
				"previous_from": prev[0] if prev else start,
				"previous_to": prev[1] if prev else None,
			}
	return None


def cycle_label(day, scope):
	"""'current', 'previous' or None for a day, given scope_cycles()."""
	if not scope or not day:
		return None
	day = getdate(day)
	if scope["current_from"] <= day <= scope["current_to"]:
		return "current"
	if scope["previous_to"] and scope["previous_from"] <= day <= scope["previous_to"]:
		return "previous"
	return None


def context(user=None):
	"""Resolve user -> employee -> shift. Raises Blocked with a UI-safe reason."""
	user = user or frappe.session.user
	if user == "Guest":
		raise Blocked("not_logged_in", _("Please log in."))
	settings = get_settings()
	employee = get_employee(user)
	now = now_datetime()
	shift = get_shift(employee, now.date())
	work_tz = employee.work_tz
	return frappe._dict(
		user=user, employee=employee, shift=shift, settings=settings, now=now,
		work_tz=work_tz, work_today=work_day(now, work_tz),
	)


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
		"from_time": with_offset(log.from_time),
		"to_time": with_offset(log.to_time) if log.to_time else None,
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
