import frappe


def execute():
	"""Add index on sales_order field in Pick List Item for faster dashboard count queries."""
	table = "tabPick List Item"
	index_name = "sales_order"

	if frappe.db.has_index(table, index_name):
		return

	frappe.db.add_index("Pick List Item", ["sales_order"])
