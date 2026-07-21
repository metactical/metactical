"""
Add back-reference fields to Purchase Receipt Item so mark_source_lines_received
knows which SOC/INS row each PR line came from.
"""
import frappe


FIELDS = [
	{
		"fieldname": "neb_source_doctype",
		"fieldtype": "Data",
		"label": "Source Doctype",
		"read_only": 1,
		"hidden": 1,
		"insert_after": "purchase_order_item",
	},
	{
		"fieldname": "neb_source_name",
		"fieldtype": "Data",
		"label": "Source Document",
		"read_only": 1,
		"hidden": 1,
		"insert_after": "neb_source_doctype",
	},
	{
		"fieldname": "neb_source_detail",
		"fieldtype": "Data",
		"label": "Source Row Name",
		"read_only": 1,
		"hidden": 1,
		"insert_after": "neb_source_name",
	},
	{
		"fieldname": "neb_box_no",
		"fieldtype": "Data",
		"label": "Box No",
		"read_only": 1,
		"insert_after": "neb_source_detail",
	},
]


def execute():
	for field in FIELDS:
		if frappe.db.exists("Custom Field", f"Purchase Receipt Item-{field['fieldname']}"):
			continue
		frappe.get_doc({
			"doctype": "Custom Field",
			"dt": "Purchase Receipt Item",
			**field,
		}).insert(ignore_permissions=True)

	frappe.db.commit()
