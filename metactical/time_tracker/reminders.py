"""Forgot to clock out: reminder (email / SMS) with a one-tap link, and an automatic close as a safety net.

When an entry is created its follow-up time is worked out once (`schedule_followup`). Every ten minutes `run()` makes
one indexed lookup for open entries whose follow-up is due, and returns at once if there are none:

1. `reminder_minutes_after_shift_end` after the scheduled end (default 15): send a reminder with a link.
2. `auto_close_hours_after_shift_end` after the scheduled end (default 4): close the entry AT THE SCHEDULED END,
   flag it Auto Closed, and tell the employee. An approver can confirm or change the time.

The link carries a signed, expiring token. It needs no login and can only do one thing: close that one open
entry at the moment it is clicked. Someone who left earlier clocks out and then asks for a correction as usual.
Setting a minutes/hours value to 0 switches that step off.
"""

import base64
import datetime as dt
import hashlib
import hmac
import time

import frappe
from frappe import _
from frappe.utils import get_datetime

from metactical.time_tracker import core

LINK_VALID_HOURS = 48
IGNORE_OLDER_THAN_DAYS = 7  # entries older than this are old business: the migrate patch deals with them


# ---- the signed link ----------------------------------------------------------------------


class InvalidLink(frappe.ValidationError):
	pass


def _key():
	from frappe.utils.password import get_encryption_key

	return get_encryption_key().encode()


def _sign(payload):
	return hmac.new(_key(), payload.encode(), hashlib.sha256).hexdigest()[:40]


def make_token(log_name, valid_hours=LINK_VALID_HOURS):
	payload = f"{log_name}.{int(time.time()) + int(valid_hours * 3600)}"
	return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=") + "." + _sign(payload)


def read_token(token):
	"""The Clockin Log name a valid, unexpired token was made for. Anything else raises InvalidLink."""
	try:
		body, sig = str(token).split(".", 1)
		payload = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)).decode()
		name, expiry = payload.rsplit(".", 1)
		if not hmac.compare_digest(sig, _sign(payload)):
			raise ValueError("signature")
		if int(expiry) < time.time():
			raise ValueError("expired")
	except Exception:
		raise InvalidLink(_("This link is not valid or has expired.")) from None
	return name


def clockout_url(log_name):
	return f"{frappe.utils.get_url()}/trackerv2/clockout?t={make_token(log_name)}"


# ---- sending ------------------------------------------------------------------------------


def _contacts(user):
	emp = frappe.db.get_value(
		"Employee", {"user_id": user},
		["employee_name", "company_email", "personal_email", "cell_number"], as_dict=True,
	) or frappe._dict()
	email = emp.get("company_email") or emp.get("personal_email") or (user if "@" in user else None)
	return frappe._dict(name=(emp.get("employee_name") or user).split(" ")[0], email=email, phone=emp.get("cell_number"))


def _sms_available():
	return bool(frappe.db.get_single_value("SMS Settings", "sms_gateway_url"))


def send(user, subject, html, sms_text):
	"""Email and, when a gateway is configured and the employee has a cell number, SMS. Returns the channels used."""
	c = _contacts(user)
	used = []
	if c.email:
		try:
			frappe.sendmail(recipients=[c.email], subject=subject, message=html, now=False)
			used.append("email")
		except Exception:
			frappe.log_error("Time clock reminder email failed", frappe.get_traceback())
	if c.phone and _sms_available():
		try:
			from frappe.core.doctype.sms_settings.sms_settings import send_sms

			send_sms([c.phone], sms_text)
			used.append("sms")
		except Exception:
			frappe.log_error("Time clock reminder SMS failed", frappe.get_traceback())
	return used


def send_reminder(log):
	c = _contacts(log.user)
	url = clockout_url(log.name)
	since = get_datetime(log.from_time).strftime("%a %I:%M %p").replace(" 0", " ")
	html = (
		f"<p>Hi {frappe.utils.escape_html(c.name)},</p>"
		f"<p>You clocked in at <b>{since}</b> and haven't clocked out yet.</p>"
		f'<p><a href="{url}">Clock me out now</a></p>'
		"<p>If you left earlier, use the link, then log in to the Time Clock and ask for a correction.</p>"
	)
	return send(log.user, _("Did you forget to clock out?"), html, f"You're still clocked in since {since}. Clock out: {url}")


def send_auto_closed(log, closed_at):
	c = _contacts(log.user)
	at = get_datetime(closed_at).strftime("%a %I:%M %p").replace(" 0", " ")
	html = (
		f"<p>Hi {frappe.utils.escape_html(c.name)},</p>"
		f"<p>You were still clocked in, so we closed your entry at the end of your shift (<b>{at}</b>).</p>"
		"<p>If that isn't right, open the Time Clock and ask for a correction.</p>"
	)
	return send(log.user, _("Your time entry was closed"), html, f"You were still clocked in. We closed your entry at {at}. Wrong? Ask for a correction in the Time Clock.")


# ---- scheduling: decide the follow-up time ONCE, when the entry opens ---------------------------------------


def _first_due(end, settings):
	"""The first follow-up moment after a scheduled end: the reminder, else the auto-close, else none."""
	if settings.reminder_minutes > 0:
		return end + dt.timedelta(minutes=settings.reminder_minutes)
	if settings.auto_close_hours > 0:
		return end + dt.timedelta(hours=settings.auto_close_hours)
	return None


def schedule_followup(doc, settings=None):
	"""Called when an entry is created (every way of creating one): store when it is next worth looking at."""
	if doc.has_clocked_out:
		return
	settings = settings or core.get_settings()
	end = core.expected_end_for(doc.user, doc.from_time, settings)
	due = _first_due(end, settings) if end else None
	if due:
		frappe.db.set_value("Clockin Log", doc.name, "followup_due_on", due, update_modified=False)


# ---- the scheduled job --------------------------------------------------------------------------------------
#
# It runs every 10 minutes, but an idle run costs ONE indexed lookup and returns: it only does anything when an
# open entry has a follow-up that is due. Nothing here re-enqueues itself, and every entry it touches either
# acts or has its due time moved on or cleared, so no entry can be picked up twice for the same step.

BATCH = 200


def run(user=None):
	"""The scheduled job. `user` limits it to one person's entries (tests, or a manual nudge); the schedule passes none."""
	now = core.now_datetime()
	filters = {
		"has_clocked_out": 0,
		"followup_due_on": ["<=", now],
		"from_time": [">=", now - dt.timedelta(days=IGNORE_OLDER_THAN_DAYS)],
	}
	if user:
		filters["user"] = user
	due = frappe.get_all(
		"Clockin Log",
		filters=filters,
		fields=["name", "user", "from_time", "reminder_sent_on"],
		limit=BATCH,
	)
	if not due:
		return  # nobody clocked in, or nothing due yet: the whole cost of an idle run
	settings = core.get_settings()
	for row in due:
		try:
			process(row, settings, now)
		except Exception:
			frappe.log_error(f"Time clock follow-up failed for {row.name}", frappe.get_traceback())
			# do not leave it due: a broken row must not be retried every ten minutes
			frappe.db.set_value("Clockin Log", row.name, "followup_due_on", None, update_modified=False)
	frappe.db.commit()


def process(row, settings, now):
	end = core.expected_end_for(row.user, row.from_time, settings)
	if end is None:
		_set_due(row.name, None)  # no shift to measure against
		return
	reminder_at = end + dt.timedelta(minutes=settings.reminder_minutes) if settings.reminder_minutes > 0 else None
	close_at = end + dt.timedelta(hours=settings.auto_close_hours) if settings.auto_close_hours > 0 else None

	if close_at and now >= close_at:
		auto_close(row.name, end)  # closes the entry, so it drops out of the next lookup
		return

	reminded = bool(row.reminder_sent_on)
	if reminder_at and now >= reminder_at and not reminded:
		send_reminder(frappe.get_doc("Clockin Log", row.name))
		frappe.db.set_value("Clockin Log", row.name, "reminder_sent_on", now, update_modified=False)
		reminded = True

	# next moment worth looking at (strictly in the future), or nothing
	pending = [t for t in (None if reminded else reminder_at, close_at) if t and t > now]
	_set_due(row.name, min(pending) if pending else None)


def _set_due(name, when):
	frappe.db.set_value("Clockin Log", name, "followup_due_on", when, update_modified=False)


def auto_close(log_name, scheduled_end):
	"""Close the entry at the scheduled end (never before it started) and flag it for an approver to confirm."""
	doc = frappe.get_doc("Clockin Log", log_name)
	if doc.has_clocked_out:
		return
	closed_at = max(get_datetime(scheduled_end), get_datetime(doc.from_time) + dt.timedelta(minutes=1))
	doc.to_time = closed_at
	doc.has_clocked_out = 1
	doc.auto_closed = 1
	doc.closed_via = "auto"
	doc.followup_due_on = None
	doc.save(ignore_permissions=True)
	send_auto_closed(doc, closed_at)
