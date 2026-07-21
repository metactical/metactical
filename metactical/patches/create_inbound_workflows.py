import frappe


STATES = [
	"Pending Review",
	"Confirmed",
	"Discrepancy Hold",
	"In Transit",
	"Received",
]

ACTIONS = [
	"Submit for Review",
	"Confirm",
	"Mark In Transit",
	"Mark Received",
	"Flag Discrepancy",
]

SOC_WORKFLOW = {
	"workflow_name": "Supplier Order Confirmation Approval",
	"document_type": "Supplier Order Confirmation",
	"states": [
		{"state": "Draft",            "doc_status": "0", "allow_edit": "Purchase User"},
		{"state": "Pending Review",   "doc_status": "0", "allow_edit": "Purchase User"},
		{"state": "Confirmed",        "doc_status": "1", "allow_edit": "Purchase Manager"},
		{"state": "Discrepancy Hold", "doc_status": "0", "allow_edit": "Purchase Manager"},
	],
	"transitions": [
		{
			"state": "Draft",
			"action": "Submit for Review",
			"next_state": "Pending Review",
			"allowed": "Purchase User",
			"allow_self_approval": 1,
		},
		{
			"state": "Pending Review",
			"action": "Confirm",
			"next_state": "Confirmed",
			"allowed": "Purchase User",
			"allow_self_approval": 1,
		},
		{
			"state": "Pending Review",
			"action": "Flag Discrepancy",
			"next_state": "Discrepancy Hold",
			"allowed": "Purchase User",
			"allow_self_approval": 1,
		},
		{
			"state": "Discrepancy Hold",
			"action": "Confirm",
			"next_state": "Confirmed",
			"allowed": "Purchase Manager",
			"allow_self_approval": 1,
		},
	],
}

INS_WORKFLOW = {
	"workflow_name": "Inbound Shipment Tracking",
	"document_type": "Inbound Shipment",
	"states": [
		{"state": "Draft",          "doc_status": "0", "allow_edit": "Purchase User"},
		{"state": "Pending Review", "doc_status": "0", "allow_edit": "Purchase User"},
		{"state": "In Transit",     "doc_status": "0", "allow_edit": "Purchase User"},
		{"state": "Received",       "doc_status": "1", "allow_edit": "Purchase User"},
	],
	"transitions": [
		{
			"state": "Draft",
			"action": "Submit for Review",
			"next_state": "Pending Review",
			"allowed": "Purchase User",
			"allow_self_approval": 1,
		},
		{
			"state": "Pending Review",
			"action": "Mark In Transit",
			"next_state": "In Transit",
			"allowed": "Purchase User",
			"allow_self_approval": 1,
		},
		{
			"state": "In Transit",
			"action": "Mark Received",
			"next_state": "Received",
			"allowed": "Purchase User",
			"allow_self_approval": 1,
		},
	],
}


def _ensure_states_and_actions():
	for state in STATES:
		if not frappe.db.exists("Workflow State", state):
			frappe.get_doc({"doctype": "Workflow State", "workflow_state_name": state}).insert(ignore_permissions=True)

	for action in ACTIONS:
		if not frappe.db.exists("Workflow Action Master", action):
			frappe.get_doc({"doctype": "Workflow Action Master", "workflow_action_name": action}).insert(ignore_permissions=True)


def _create_workflow(definition):
	name = definition["workflow_name"]
	if frappe.db.exists("Workflow", {"workflow_name": name}):
		return
	frappe.get_doc({
		"doctype": "Workflow",
		"is_active": 1,
		"override_status": 0,
		"send_email_alert": 0,
		"workflow_state_field": "workflow_state",
		**definition,
	}).insert(ignore_permissions=True)


def execute():
	_ensure_states_and_actions()
	_create_workflow(SOC_WORKFLOW)
	_create_workflow(INS_WORKFLOW)
	frappe.db.commit()
