import json, frappe
from frappe import _

@frappe.whitelist()
def execute_event(doc: str):
	user = frappe.session.user
	doc = json.loads(doc)

	# get users the doucment is share to
	shared = frappe.get_all(
        "DocShare",
        filters={"share_doctype": doc["doctype"], "share_name": doc["name"]},
        fields=["user", "read", "write", "share", "submit"]
    )
 
	# Check if user has write access via sharing
	has_write_access = any(s["user"] == user and s["write"] for s in shared)

	# Check if user has System Manager role
	is_system_manager = "System Manager" in frappe.get_roles(user)

	if not (has_write_access or is_system_manager):
		frappe.throw(_("You do not have permission to execute this event.")) 
	
	frappe.get_doc("Scheduled Job Type", doc.get("name")).enqueue(force=True)
	return doc
