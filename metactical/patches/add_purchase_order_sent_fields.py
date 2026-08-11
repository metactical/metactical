import frappe


FIELDS = [
	{
		"fieldname": "custom_sent_section",
		"fieldtype": "Section Break",
		"label": "Supplier Transmission",
		"insert_after": "terms",
	},
	{
		"fieldname": "custom_sent_on",
		"fieldtype": "Datetime",
		"label": "Sent On",
		"read_only": 1,
		"insert_after": "custom_sent_section",
	},
	{
		"fieldname": "custom_sent_by",
		"fieldtype": "Link",
		"label": "Sent By",
		"options": "User",
		"read_only": 1,
		"insert_after": "custom_sent_on",
	},
	{
		"fieldname": "custom_col_sent",
		"fieldtype": "Column Break",
		"insert_after": "custom_sent_by",
	},
	{
		"fieldname": "custom_sent_method",
		"fieldtype": "Select",
		"label": "Sent Method",
		"options": "\nEmail\nPhone\nPortal\nEDI\nOther",
		"insert_after": "custom_col_sent",
	},
	{
		"fieldname": "custom_supplier_ack_expected",
		"fieldtype": "Check",
		"label": "Supplier Acknowledgement Expected",
		"insert_after": "custom_sent_method",
	},
]


def execute():
	for field in FIELDS:
		if frappe.db.exists("Custom Field", f"Purchase Order-{field['fieldname']}"):
			continue
		cf = frappe.get_doc({
			"doctype": "Custom Field",
			"dt": "Purchase Order",
			**field,
		})
		cf.insert(ignore_permissions=True)

	frappe.db.commit()
