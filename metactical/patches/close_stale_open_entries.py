import frappe

from metactical.time_tracker import core


def execute():
	"""Close clock entries nobody ever clocked out of, when they are older than the previous pay cycle.

	Those periods are already paid, so the entry is closed at zero hours (not invented hours) and marked
	Auto Closed. No Employee Checkin OUT is created. Entries in the current and previous cycle are NOT
	touched: someone can still correct those.
	"""
	scope = core.scope_cycles(core.today())
	if not scope:
		return  # no pay cycles configured: nothing safe to compare against
	paid_before = scope["previous_from"]
	frappe.db.sql(
		"""update `tabClockin Log`
		set to_time = from_time, has_clocked_out = 1, total_hours = 0, auto_closed = 1
		where has_clocked_out = 0 and date < %s""",
		paid_before,
	)
