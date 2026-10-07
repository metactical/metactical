import frappe

# Schedules seen in the clock history (about 62 people over 12 months, deverp):
#   first punch  10:00 35%, 09:00 20%, 09:30 8%, 11:00 3%
#   last punch   19:00 17%, 17:00 13%, 20:00 11%, 18:00 10%
#   day length   under 6h 21%, 6-8.5h 45%, 8.5-10.5h 27%, 10.5-12.5h 4%
#   pattern      mostly 5 days x 7.5-8h or 4 days x 7-8h; some 6 days
# Canada allows 8h x 5 days or 10h x 4 days without overtime, and some people work 12-14h days.
# The window includes the lunch break; Expected Hours is the paid time inside it.
STANDARD = [
	# name, start, end, expected paid hours
	("8h Day 09:00-17:00", "09:00:00", "17:00:00", 8),
	("8h Retail 10:00-19:00", "10:00:00", "19:00:00", 8),
	("8h Late 12:00-20:00", "12:00:00", "20:00:00", 8),
	("10h Day 09:00-19:00", "09:00:00", "19:00:00", 10),
	("10h Late 10:00-20:00", "10:00:00", "20:00:00", 10),
	("12h Long 08:00-20:00", "08:00:00", "20:00:00", 12),
	("14h Extended 08:00-22:00", "08:00:00", "22:00:00", 14),
]


def execute():
	"""Add the standard schedules. Existing Shift Types (Flex Shift, Store Shift, ...) are left alone,
	and nobody is reassigned: HR moves people onto these with the Shift Assignment tool."""
	for name, start, end, hours in STANDARD:
		if frappe.db.exists("Shift Type", name):
			continue
		frappe.get_doc(
			{
				"doctype": "Shift Type",
				"name": name,
				"start_time": start,
				"end_time": end,
				"tt_expected_hours": hours,
			}
		).insert(ignore_permissions=True)
