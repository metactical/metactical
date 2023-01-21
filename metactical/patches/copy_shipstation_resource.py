import frappe

def execute():
	frappe.reload_doc('metactical', 'doctype', 'Shipstation API Requests')
	frappe.db.sql("""update `tabShipstation API Requests` SET resource_url=start_date, resource_type=end_date""")
