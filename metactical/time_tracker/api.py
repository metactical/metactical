"""Whitelisted endpoints for the Time Clock page. Snake_case, same shapes everywhere.

Every clock action returns the full new state, so the screen never has to guess what happened.
"""

import frappe
from frappe import _
from frappe.utils import add_days, get_datetime, getdate, now_datetime

from metactical.time_tracker import core
from metactical.time_tracker.core import Blocked


def _fail(title):
	frappe.log_error(title, frappe.get_traceback())


def _blocked_state(b, user):
	return {
		"server_now": str(now_datetime()),
		"status": "blocked",
		"blockers": [{"code": b.code, "message": b.message}],
		"user": user,
	}


# ---- state --------------------------------------------------------------------------------


def build_state(ctx, notice=None):
	now, user = ctx.now, ctx.user
	logs = core.logs_for_day(user, now.date())
	opened = core.open_logs(user)
	current = opened[0] if opened else None

	state_key, shift_start, shift_end = core.shift_window(ctx.shift, now, ctx.settings.early_minutes)
	can_in, reason = True, None
	if current:
		can_in, reason = False, _("Already clocked in")
	elif ctx.settings.enforce_window and state_key != "open":
		can_in = False
		reason = _("Your shift starts at {0}").format(shift_start.strftime("%I:%M %p").lstrip("0"))
		if state_key == "after":
			reason = _("Your shift is over. Next shift starts {0}").format(
				shift_start.strftime("%a %I:%M %p").replace(" 0", " ")
			)

	today_hours = sum(core.log_hours(l, now) for l in logs)
	# A shift that crossed midnight keeps its open log on yesterday's date; count it in today's total too.
	if current and getdate(current.date) != now.date():
		today_hours += core.log_hours(current, now)
		logs = logs + [current]

	cycle = None
	try:
		start, end = core.get_cycle(now.date(), ctx.settings)
		totals = core.day_totals(user, start, end, now)
		cycle = {
			"from_date": str(start),
			"to_date": str(end),
			"total_hours": round(sum(v[0] for v in totals.values()), 4),
		}
	except Blocked as b:
		cycle = {"error": b.message}

	return {
		"server_now": str(now),
		"status": "in" if current else "out",
		"user": user,
		"employee": {"name": ctx.employee.name, "employee_name": ctx.employee.employee_name},
		"shift": {
			"name": ctx.shift.name,
			"start": str(shift_start),
			"end": str(shift_end),
			"window_state": state_key,
		},
		"open_log": core.serialize_log(current, now) if current else None,
		"can_clock_in": can_in,
		"can_clock_in_reason": reason,
		"can_clock_out": bool(current),
		"today": {
			"date": str(now.date()),
			"total_hours": round(today_hours, 4),
			"logs": [core.serialize_log(l, now) for l in logs],
		},
		"cycle": cycle,
		"max_shift_hours": ctx.settings.max_shift_hours,
		"auto_logout_seconds": ctx.settings.logout_delay,
		"blockers": [],
		"notice": notice,
	}


@frappe.whitelist()
def get_state():
	try:
		return build_state(core.context())
	except Blocked as b:
		return _blocked_state(b, frappe.session.user)


# ---- clock --------------------------------------------------------------------------------


@frappe.whitelist(methods=["POST"])
def clock_in():
	ctx = core.context()
	core.lock_employee(ctx.employee.name)

	if core.open_logs(ctx.user):
		return build_state(ctx, notice=_("You were already clocked in."))

	state_key, shift_start, _end = core.shift_window(ctx.shift, ctx.now, ctx.settings.early_minutes)
	if ctx.settings.enforce_window and state_key != "open":
		frappe.throw(
			_("Clock in opens {0} minutes before your shift ({1}).").format(
				ctx.settings.early_minutes, shift_start.strftime("%I:%M %p").lstrip("0")
			),
			title=_("Too early"),
		)

	frappe.get_doc(
		{
			"doctype": "Clockin Log",
			"user": ctx.user,
			"date": ctx.now.date(),
			"from_time": ctx.now,
			"total_hours": 0.0,
		}
	).insert(ignore_permissions=True)
	return build_state(ctx, notice=_("Clocked in."))


@frappe.whitelist(methods=["POST"])
def clock_out():
	ctx = core.context()
	core.lock_employee(ctx.employee.name)

	opened = core.open_logs(ctx.user)
	if not opened:
		return build_state(ctx, notice=_("You were not clocked in."))

	# More than one open log should be impossible; if history left some, close them all at the same moment.
	for row in opened:
		log = frappe.get_doc("Clockin Log", row.name)
		log.to_time = ctx.now
		log.has_clocked_out = 1
		log.save(ignore_permissions=True)
	return build_state(ctx, notice=_("Clocked out."))


# ---- history ------------------------------------------------------------------------------


@frappe.whitelist()
def get_cycle(offset=0):
	"""A pay cycle with per-day hours. offset 0 = the current cycle, 1 = the one before, and so on."""
	ctx = core.context()
	offset = int(offset)
	cycles = sorted(ctx.settings.pay_cycles, key=lambda c: c[0], reverse=True)
	today = ctx.now.date()
	current_idx = next((i for i, (s, e) in enumerate(cycles) if s <= today <= e), 0)
	idx = current_idx + offset
	if not cycles or idx < 0 or idx >= len(cycles):
		return {"error": _("No pay cycle available."), "has_prev": False, "has_next": False}

	start, end = cycles[idx]
	totals = core.day_totals(ctx.user, start, end, ctx.now)
	pending = {
		str(r.date): r.n
		for r in frappe.db.sql(
			"""select l.date as date, count(*) as n from `tabCheckin Request Modification` r
			join `tabClockin Log` l on l.name = r.log
			where r.user=%s and r.status='Pending' and l.date between %s and %s group by l.date""",
			(ctx.user, start, end),
			as_dict=True,
		)
	}
	s_start, s_end = core.shift_occurrence(ctx.shift, today)
	shift_hours = core.hours_between(s_start, s_end)
	still_open = {str(core.getdate(l.date)) for l in core.open_logs(ctx.user)}
	adds = {}  # missed-time requests for days with no entry: latest per date
	# `date` on this doctype is a text field, so filter the (few) rows in Python rather than in SQL.
	for r in frappe.get_all(
		"Checkin Request Modification",
		filters={"user": ctx.user, "request_type": "Add"},
		fields=["date", "status", "review_comment"],
		order_by="creation asc",
	):
		if str(start) <= str(r.date) <= str(end):
			adds[str(r.date)] = {"status": r.status, "review_comment": r.review_comment}
	for k, v in adds.items():
		if v["status"] == "Pending":
			pending[k] = pending.get(k, 0) + 1
	days = [
		{
			"date": str(d),
			"hours": round(v[0], 4),
			"log_count": v[1],
			"add_request": adds.get(str(d)),
			"can_add": bool(d <= today and (today - d).days <= ctx.settings.backdate_days and v[1] == 0),
			"pending_requests": pending.get(str(d), 0),
			"is_today": d == today,
			# Short = worked something, finished, and clearly less than the scheduled shift
			# (a few minutes of clock-in/out jitter is not a short day). Days with no
			# entries are not flagged (we do not know which days were scheduled), and a day still
			# in progress is never short.
			"short": bool(
				shift_hours > 0 and 0 < v[0] < shift_hours - core.SHORT_DAY_TOLERANCE_HOURS and d != today and str(d) not in still_open
			),
		}
		for d, v in totals.items()
	]
	return {
		"from_date": str(start),
		"to_date": str(end),
		"shift_hours": round(shift_hours, 4),
		"total_hours": round(sum(d["hours"] for d in days), 4),
		"days": days,
		"has_prev": idx + 1 < len(cycles),
		"has_next": idx > 0,
	}


@frappe.whitelist()
def get_day(date):
	ctx = core.context()
	logs = core.logs_for_day(ctx.user, date)
	requests = {
		r.log: r
		for r in frappe.get_all(
			"Checkin Request Modification",
			filters={"user": ctx.user, "log": ["in", [l.name for l in logs] or [""]]},
			fields=["name", "log", "status", "requested_from", "requested_to", "reason", "review_comment", "modified"],
			order_by="modified asc",
		)
	}
	out = []
	for l in logs:
		item = core.serialize_log(l, ctx.now)
		r = requests.get(l.name)
		item["request"] = (
			{
				"name": r.name,
				"status": r.status,
				"requested_from": str(r.requested_from) if r.requested_from else None,
				"requested_to": str(r.requested_to) if r.requested_to else None,
				"reason": r.reason,
				"review_comment": r.review_comment,
			}
			if r
			else None
		)
		out.append(item)
	return {"date": str(getdate(date)), "logs": out, "total_hours": round(sum(i["hours"] for i in out), 4)}


# ---- corrections --------------------------------------------------------------------------


def _fmt12(d):
	return get_datetime(d).strftime("%I:%M %p").lstrip("0")


def _check_span(ctx, new_from, new_to, reason):
	reason = (reason or "").strip()
	if len(reason) < 3:
		frappe.throw(_("Please say why the time needs to change."))
	hours = core.hours_between(new_from, new_to)
	if hours <= 0:
		frappe.throw(_("Clock out must be after clock in."))
	if hours > ctx.settings.max_shift_hours:
		frappe.throw(_("That is longer than {0} hours.").format(ctx.settings.max_shift_hours))
	if new_to > ctx.now:
		frappe.throw(_("Clock out can not be in the future."))
	return reason, hours


def _assert_no_overlap(user, new_from, new_to, exclude=None):
	clash = frappe.db.sql(
		"""select name from `tabClockin Log`
		where user=%s and name!=%s and from_time < %s and coalesce(to_time, now()) > %s limit 1""",
		(user, exclude or "", new_to, new_from),
	)
	if clash:
		frappe.throw(_("Those times overlap another entry ({0}).").format(clash[0][0]))


def _approver_emails(settings):
	"""The settings address plus everyone who holds the Time Approval role."""
	emails = set()
	if settings.approver:
		emails.add(settings.approver)
	emails.update(
		frappe.get_all(
			"Has Role",
			filters={"role": APPROVER_ROLE, "parenttype": "User"},
			pluck="parent",
		)
	)
	enabled = set(frappe.get_all("User", filters={"name": ["in", list(emails) or [""]], "enabled": 1}, pluck="name"))
	return sorted(e for e in emails if e in enabled or e == settings.approver)


def _notify_approver(ctx, subject, body):
	recipients = _approver_emails(ctx.settings)
	if not recipients:
		return
	try:
		frappe.sendmail(recipients=recipients, subject=subject, message=body, now=False)
	except Exception:
		_fail("Time change request email failed")


@frappe.whitelist(methods=["POST"])
def request_missed_punch(date, from_time, to_time, reason):
	"""Employee asks to add an entry for a day they never clocked in at all."""
	ctx = core.context()
	day = getdate(date)
	today = ctx.now.date()
	if day > today:
		frappe.throw(_("You can not add time for a future day."))
	if (today - day).days > ctx.settings.backdate_days:
		frappe.throw(
			_("You can only add time up to {0} days back. Ask HR for older days.").format(ctx.settings.backdate_days)
		)

	new_from, new_to = get_datetime(from_time), get_datetime(to_time)
	if new_from.date() != day:
		frappe.throw(_("Clock in must be on {0}.").format(day))
	reason, hours = _check_span(ctx, new_from, new_to, reason)
	_assert_no_overlap(ctx.user, new_from, new_to)
	if frappe.db.exists(
		"Checkin Request Modification",
		{"user": ctx.user, "request_type": "Add", "date": str(day), "status": "Pending"},
	):
		frappe.throw(_("You already have a request waiting for {0}.").format(day))

	req = frappe.get_doc(
		{
			"doctype": "Checkin Request Modification",
			"request_type": "Add",
			"user": ctx.user,
			"date": str(day),
			"status": "Pending",
			"reason": reason,
			"requested_from": new_from,
			"requested_to": new_to,
			"current_checkin": "-",
			"current_checkout": "-",
			"current_total_hours": "0",
			"requested_checkin": _fmt12(new_from),
			"requested_checkout": _fmt12(new_to),
			"requested_total_hours": str(round(hours, 2)),
			"requested_checkin_military": new_from.strftime("%H:%M:%S"),
			"requested_checkout_military": new_to.strftime("%H:%M:%S"),
		}
	).insert(ignore_permissions=True)
	_notify_approver(
		ctx,
		_("Missed time request from {0}").format(ctx.employee.employee_name),
		_("{0} asked to add time on {1}: {2} - {3}.<br>Reason: {4}<br>Review it on the Time Clock page.").format(
			ctx.employee.employee_name, day, _fmt12(new_from), _fmt12(new_to), frappe.utils.escape_html(reason)
		),
	)
	return {"name": req.name, "status": req.status}


@frappe.whitelist(methods=["POST"])
def request_correction(log, from_time, to_time, reason):
	"""Employee asks for different in/out times on one of their own logs."""
	ctx = core.context()
	doc = frappe.get_doc("Clockin Log", log)
	if doc.user != ctx.user:
		frappe.throw(_("You can only correct your own time."), frappe.PermissionError)
	if not doc.has_clocked_out:
		frappe.throw(_("Clock out first, then request a correction."))
	new_from, new_to = get_datetime(from_time), get_datetime(to_time)
	reason, hours = _check_span(ctx, new_from, new_to, reason)
	if frappe.db.exists("Checkin Request Modification", {"log": log, "status": "Pending"}):
		frappe.throw(_("This entry already has a request waiting for approval."))

	req = frappe.get_doc(
		{
			"doctype": "Checkin Request Modification",
			"user": ctx.user,
			"date": str(doc.date),
			"log": log,
			"status": "Pending",
			"reason": reason,
			"requested_from": new_from,
			"requested_to": new_to,
			# legacy fields the old approval page and emails still read
			"current_checkin": _fmt12(doc.from_time),
			"current_checkout": _fmt12(doc.to_time),
			"current_total_hours": str(round(doc.total_hours or 0, 2)),
			"requested_checkin": _fmt12(new_from),
			"requested_checkout": _fmt12(new_to),
			"requested_total_hours": str(round(hours, 2)),
			"requested_checkin_military": new_from.strftime("%H:%M:%S"),
			"requested_checkout_military": new_to.strftime("%H:%M:%S"),
		}
	).insert(ignore_permissions=True)

	recipients = _approver_emails(ctx.settings)
	if recipients:
		try:
			frappe.sendmail(
				recipients=recipients,
				subject=_("Time change request from {0}").format(ctx.employee.employee_name),
				message=_(
					"{0} asked to change {1}: {2} - {3} becomes {4} - {5}.<br>Reason: {6}<br>"
					"Review it on the Time Clock page."
				).format(
					ctx.employee.employee_name,
					doc.date,
					_fmt12(doc.from_time),
					_fmt12(doc.to_time),
					_fmt12(new_from),
					_fmt12(new_to),
					frappe.utils.escape_html(reason),
				),
				now=False,
			)
		except Exception:
			_fail("Time change request email failed")
	return {"name": req.name, "status": req.status}


APPROVER_ROLE = "Time Approval"


def can_review(user=None):
	"""Anyone with the Time Approval role sees and decides every request. HR Manager, System Manager and
	the address in Time Tracker Settings keep working as before."""
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	roles = set(frappe.get_roles(user))
	if roles & {APPROVER_ROLE, "System Manager", "HR Manager"}:
		return True
	return bool(core.get_settings().approver) and core.get_settings().approver.lower() == user.lower()


def assert_can_review():
	if not can_review():
		frappe.throw(_("Only the time approver can review requests."), frappe.PermissionError)


@frappe.whitelist()
def get_pending_requests():
	assert_can_review()
	rows = frappe.get_all(
		"Checkin Request Modification",
		filters={"status": "Pending"},
		fields=[
			"name", "user", "date", "log", "request_type", "reason", "requested_from", "requested_to",
			"current_checkin", "current_checkout", "current_total_hours", "requested_total_hours",
		],
		order_by="creation asc",
	)
	names = dict(
		frappe.get_all("Employee", filters={"user_id": ["in", [r.user for r in rows] or [""]]},
					   fields=["user_id", "employee_name"], as_list=True)
	)
	for r in rows:
		r["employee_name"] = names.get(r.user) or r.user
	return rows


@frappe.whitelist(methods=["POST"])
def review_request(name, decision, comment=None):
	assert_can_review()
	if decision not in ("Approved", "Declined"):
		frappe.throw(_("Decision must be Approved or Declined."))
	req = frappe.get_doc("Checkin Request Modification", name)
	if req.status != "Pending":
		frappe.throw(_("This request was already {0}.").format(req.status.lower()))
	if req.user == frappe.session.user and frappe.session.user not in ("Administrator",):
		frappe.throw(_("You cannot approve your own request."), frappe.PermissionError)

	if decision == "Approved":
		apply_request(req)

	req.status = decision
	req.reviewed_by = frappe.session.user
	req.reviewed_on = now_datetime()
	req.review_comment = (comment or "").strip() or None
	req.save(ignore_permissions=True)
	return {"name": req.name, "status": req.status}


def apply_request(req):
	if req.get("request_type") == "Add":
		apply_missed_punch(req)
	else:
		apply_correction(req)


def apply_missed_punch(req):
	"""Create the closed entry the employee asked for, refusing overlaps that appeared since."""
	new_from, new_to = get_datetime(req.requested_from), get_datetime(req.requested_to)
	_assert_no_overlap(req.user, new_from, new_to)
	frappe.get_doc(
		{
			"doctype": "Clockin Log",
			"user": req.user,
			"date": new_from.date(),
			"from_time": new_from,
			"to_time": new_to,
			"has_clocked_out": 1,
		}
	).insert(ignore_permissions=True)


def apply_correction(req):
	"""Write the approved times onto the log, refusing anything that would overlap another entry."""
	if not req.requested_from or not req.requested_to:
		frappe.throw(_("This is an older request without exact times. Edit the Clockin Log directly."))
	log = frappe.get_doc("Clockin Log", req.log)
	new_from, new_to = get_datetime(req.requested_from), get_datetime(req.requested_to)
	_assert_no_overlap(log.user, new_from, new_to, exclude=log.name)
	log.from_time = new_from
	log.to_time = new_to
	log.date = new_from.date()
	log.save(ignore_permissions=True)


@frappe.whitelist()
def get_my_permissions():
	allowed = can_review()
	return {
		"can_review": allowed,
		"pending_count": frappe.db.count("Checkin Request Modification", {"status": "Pending"}) if allowed else 0,
	}


@frappe.whitelist()
def get_requests(tab="Pending"):
	"""The approvals screen: every request (no team filtering) with the context to decide on it."""
	assert_can_review()
	decided = tab == "Decided"
	filters = {"status": ["in", ["Approved", "Declined"]]} if decided else {"status": "Pending"}
	rows = frappe.get_all(
		"Checkin Request Modification",
		filters=filters,
		fields=[
			"name", "user", "request_type", "status", "reason", "log", "date", "creation", "reviewed_by",
			"reviewed_on", "review_comment", "requested_from", "requested_to", "current_checkin",
			"current_checkout", "requested_checkin_military", "requested_checkout_military",
		],
		order_by="reviewed_on desc, modified desc" if decided else "creation asc",
		limit=200,
	)

	users = [r.user for r in rows]
	employees = {
		r.user_id: r
		for r in frappe.get_all(
			"Employee", filters={"user_id": ["in", users or [""]]}, fields=["user_id", "name", "employee_name"]
		)
	}
	today = now_datetime().date()
	shift_of = {}
	if employees:
		for emp, shift_type in frappe.db.sql(
			"""select employee, shift_type from `tabShift Assignment`
			where docstatus=1 and status='Active' and start_date <= %(d)s and (end_date is null or end_date >= %(d)s)
				and employee in %(emps)s order by start_date asc""",
			{"d": today, "emps": [e.name for e in employees.values()]},
		):
			shift_of[emp] = shift_type  # latest start_date wins (ordered ascending)
	reviewer_names = {
		u.name: u.full_name
		for u in frappe.get_all(
			"User", filters={"name": ["in", [r.reviewed_by for r in rows if r.reviewed_by] or [""]]},
			fields=["name", "full_name"],
		)
	}

	out = []
	for r in rows:
		emp = employees.get(r.user)
		log = frappe.db.get_value("Clockin Log", r.log, ["date", "from_time", "to_time", "total_hours"], as_dict=True) if r.log else None
		day = getdate(log.date) if log else _iso_or_none(r.date)
		new_from = get_datetime(r.requested_from) if r.requested_from else None
		new_to = get_datetime(r.requested_to) if r.requested_to else None
		if (new_from is None or new_to is None) and day:  # request made by the older page: only HH:MM were kept
			new_from = new_from or get_datetime(f"{day} {r.requested_checkin_military}")
			new_to = new_to or get_datetime(f"{day} {r.requested_checkout_military}")
		requested_hours = core.hours_between(new_from, new_to) if new_from and new_to else None
		current_hours = float(log.total_hours or 0) if log else None
		same_day = (
			[
				{
					"from_time": str(l.from_time),
					"to_time": str(l.to_time) if l.to_time else None,
					"hours": round(core.log_hours(l, now_datetime()), 4),
					"is_this_entry": l.name == r.log,
				}
				for l in core.logs_for_day(r.user, day)
			]
			if day
			else []
		)
		out.append(
			{
				"name": r.name,
				"user": r.user,
				"employee_name": emp.employee_name if emp else r.user,
				"shift": shift_of.get(emp.name) if emp else None,
				"request_type": r.request_type or "Change",
				"status": r.status,
				"reason": r.reason,
				"date": str(day) if day else None,
				"requested_at": str(r.creation),
				"current_from": str(log.from_time) if log else None,
				"current_to": str(log.to_time) if log and log.to_time else None,
				"current_hours": round(current_hours, 4) if current_hours is not None else None,
				"requested_from": str(new_from) if new_from else None,
				"requested_to": str(new_to) if new_to else None,
				"requested_hours": round(requested_hours, 4) if requested_hours is not None else None,
				"delta_hours": round(requested_hours - (current_hours or 0), 4) if requested_hours is not None else None,
				"same_day": same_day,
				"reviewed_by_name": reviewer_names.get(r.reviewed_by) or r.reviewed_by,
				"reviewed_on": str(r.reviewed_on) if r.reviewed_on else None,
				"review_comment": r.review_comment,
			}
		)

	return {
		"rows": out,
		"pending_count": frappe.db.count("Checkin Request Modification", {"status": "Pending"}),
		"decided_count": frappe.db.count("Checkin Request Modification", {"status": ["in", ["Approved", "Declined"]]}),
	}


def _iso_or_none(value):
	try:
		return getdate(value) if value else None
	except Exception:
		return None
