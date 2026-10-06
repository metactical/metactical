import datetime as dt

import frappe

from metactical.time_tracker import core, reminders


def execute():
	"""Entries open at deploy time were created before follow-ups existed: give the recent ones a due time."""
	settings = core.get_settings()
	since = core.now_datetime() - dt.timedelta(days=reminders.IGNORE_OLDER_THAN_DAYS)
	for row in frappe.get_all("Clockin Log", filters={"has_clocked_out": 0, "from_time": [">=", since]}, fields=["name", "user", "from_time"]):
		reminders.schedule_followup(frappe._dict(row, has_clocked_out=0), settings)
