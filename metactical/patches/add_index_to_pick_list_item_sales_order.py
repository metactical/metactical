import frappe


def execute():
	"""Add composite index on (sales_order, parent) in Pick List Item for faster dashboard count queries.
	
	The Sales Order dashboard queries Pick Lists via child table, requiring:
	SELECT DISTINCT parent FROM `tabPick List Item` WHERE sales_order = 'SO-XXX'
	
	A composite index on (sales_order, parent) allows this query to be answered entirely from the index.
	"""
	table = "tabPick List Item"
	
	# Add composite index for dashboard queries
	composite_index_name = "idx_sales_order_parent"
	if not frappe.db.has_index(table, composite_index_name):
		frappe.db.sql("""
			CREATE INDEX idx_sales_order_parent 
			ON `tabPick List Item` (sales_order, parent)
		""")