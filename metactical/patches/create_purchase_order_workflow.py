import frappe


STATES = [
	"Draft",
	"Pending L1 Approval",
	"Pending L2 Approval",
	"Approved",
	"Rejected",
	"Sent to Supplier",
]

ACTIONS = [
	"Submit for Approval",
	"Approve",
	"Reject",
	"Reset to Draft",
	"Mark as Sent",
]


def execute():
	for state in STATES:
		if not frappe.db.exists("Workflow State", state):
			frappe.get_doc({"doctype": "Workflow State", "workflow_state_name": state}).insert(ignore_permissions=True)

	for action in ACTIONS:
		if not frappe.db.exists("Workflow Action Master", action):
			frappe.get_doc({"doctype": "Workflow Action Master", "workflow_action_name": action}).insert(ignore_permissions=True)

	existing = frappe.db.exists("Workflow", {"workflow_name": "Purchase Order Approval"})
	if existing:
		# Patch existing workflow to add Sent to Supplier if not already there
		wf = frappe.get_doc("Workflow", existing)
		state_names = [s.state for s in wf.states]
		if "Sent to Supplier" not in state_names:
			wf.append("states", {"state": "Sent to Supplier", "doc_status": "1", "allow_edit": "Purchase User"})
			wf.append("transitions", {
				"state": "Approved",
				"action": "Mark as Sent",
				"next_state": "Sent to Supplier",
				"allowed": "Purchase User",
				"allow_self_approval": 1,
			})
			wf.save(ignore_permissions=True)
			frappe.db.commit()
		return

	doc = frappe.get_doc({
		"doctype": "Workflow",
		"workflow_name": "Purchase Order Approval",
		"document_type": "Purchase Order",
		"is_active": 1,
		"override_status": 0,
		"send_email_alert": 0,
		"workflow_state_field": "workflow_state",
		"states": [
			{"state": "Draft",               "doc_status": "0", "allow_edit": "Purchase User"},
			{"state": "Pending L1 Approval", "doc_status": "0", "allow_edit": "Purchase User"},
			{"state": "Pending L2 Approval", "doc_status": "0", "allow_edit": "Purchase Manager"},
			{"state": "Approved",            "doc_status": "1", "allow_edit": "Purchase Manager"},
			{"state": "Rejected",            "doc_status": "0", "allow_edit": "Purchase User"},
			{"state": "Sent to Supplier",    "doc_status": "1", "allow_edit": "Purchase User"},
		],
		"transitions": [
			{
				"state": "Draft",
				"action": "Submit for Approval",
				"next_state": "Pending L1 Approval",
				"allowed": "Purchase User",
				"allow_self_approval": 1,
			},
			{
				"state": "Pending L1 Approval",
				"action": "Approve",
				"next_state": "Pending L2 Approval",
				"allowed": "Purchase User",
				"allow_self_approval": 0,
			},
			{
				"state": "Pending L1 Approval",
				"action": "Reject",
				"next_state": "Rejected",
				"allowed": "Purchase User",
				"allow_self_approval": 1,
			},
			{
				"state": "Pending L2 Approval",
				"action": "Approve",
				"next_state": "Approved",
				"allowed": "Purchase Manager",
				"allow_self_approval": 1,
			},
			{
				"state": "Pending L2 Approval",
				"action": "Reject",
				"next_state": "Rejected",
				"allowed": "Purchase Manager",
				"allow_self_approval": 1,
			},
			{
				"state": "Rejected",
				"action": "Reset to Draft",
				"next_state": "Draft",
				"allowed": "Purchase User",
				"allow_self_approval": 1,
			},
			{
				"state": "Approved",
				"action": "Mark as Sent",
				"next_state": "Sent to Supplier",
				"allowed": "Purchase User",
				"allow_self_approval": 1,
			},
		],
	})
	doc.insert(ignore_permissions=True)
	frappe.db.commit()
