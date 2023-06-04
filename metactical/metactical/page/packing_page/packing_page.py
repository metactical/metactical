import frappe

@frappe.whitelist()
def get_delivery_from_tote(tote):
	return frappe.db.get_value('Picklist Tote', tote, 'current_delivery_note')
	
@frappe.whitelist()
def check_to_add_permission():
	has_permission = frappe.db.exists('Packing Allowed User', {"user": frappe.session.user})
	if not has_permission:
		return False
	else:
		return True
