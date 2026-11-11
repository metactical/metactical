import frappe

from metactical.time_tracker import locations


def execute():
	"""Employee 'State/Province' becomes a drop-down of ISO 3166-2 codes (CA-BC, US-TX, OTHER).

	Convert the free text already there ("BC", "British Columbia", "Texas"). A drop-down refuses to save
	any other value, so something we cannot match is blanked rather than left to block the employee
	record; the old text is kept as a comment on the Employee for HR.
	"""
	rows = frappe.db.sql(
		"select name, ais_state from `tabEmployee` where ais_state is not null and ais_state != ''", as_dict=True
	)
	for r in rows:
		code = locations.normalize_region(r.ais_state)
		if code == r.ais_state:
			continue
		frappe.db.set_value("Employee", r.name, "ais_state", code or "", update_modified=False)
		if code is None:
			frappe.get_doc(
				{
					"doctype": "Comment",
					"comment_type": "Info",
					"reference_doctype": "Employee",
					"reference_name": r.name,
					"content": "State/Province was '{0}'. It could not be matched to an ISO code, so it was cleared. "
					"Please pick the right one.".format(frappe.utils.escape_html(r.ais_state)),
				}
			).insert(ignore_permissions=True)
