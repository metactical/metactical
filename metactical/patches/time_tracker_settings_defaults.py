import frappe

# Frappe does not apply a new field's default to an existing Single doc, and saving the form afterwards
# stores 0. Set the intended defaults once, only where nothing has been stored yet.
DEFAULTS = {
	"early_clockin_minutes": 15,
	"enforce_shift_window": 1,
	"max_shift_hours": 16,
	"backdate_limit_days": 14,
}


def execute():
	for field, value in DEFAULTS.items():
		stored = frappe.db.sql(
			"select 1 from `tabSingles` where doctype='Time Tracker Settings' and field=%s", field
		)
		if not stored:
			frappe.db.set_single_value("Time Tracker Settings", field, value)
