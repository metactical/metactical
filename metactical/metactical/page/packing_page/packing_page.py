import frappe

@frappe.whitelist()
def get_delivery_from_tote(tote):
	return frappe.db.get_value('Picklist Tote', tote, 'current_delivery_note')
