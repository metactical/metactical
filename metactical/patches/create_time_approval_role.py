import frappe

ROLE = "Time Approval"


def execute():
	"""The role that can review every time change request. Give it on the User form (Roles tab)."""
	if frappe.db.exists("Role", ROLE):
		return
	frappe.get_doc({"doctype": "Role", "role_name": ROLE, "desk_access": 0, "is_custom": 1}).insert(
		ignore_permissions=True
	)
