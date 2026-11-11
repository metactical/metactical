import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	"""Shift Type gets 'Expected Hours Per Day'.

	Shift Types describe when someone may clock in; they do not always say how long a normal day is
	(deverp's Store Shift is 06:00-22:00). The Time Clock scales its day bar, and flags short days, by
	this value. Left empty, it falls back to the shift's own length, and for very wide shifts to the
	Standard Day Hours setting.
	"""
	create_custom_fields(
		{
			"Shift Type": [
				{
					"fieldname": "tt_expected_hours",
					"fieldtype": "Float",
					"label": "Expected Hours Per Day",
					"insert_after": "end_time",
					"non_negative": 1,
					"description": "Paid hours on a normal day of this schedule (e.g. 8 or 10). "
					"Leave empty to use the length of the shift.",
				}
			]
		},
		ignore_validate=True,
	)
