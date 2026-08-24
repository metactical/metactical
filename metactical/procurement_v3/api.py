# Copyright (c) 2026, Storebuilder Commerce Inc and contributors
# For license information, please see license.txt

"""Cross-cutting Procurement V3 API methods.

Whitelisted methods that belong to the V3 flow as a whole rather than to any
one doctype. Doctype-scoped APIs live on their own controllers instead --
v3_retry_po_submit and friends on Purchase Order V3, the v3_gr3_* ones on
Goods Receipt V3.
"""

import frappe


# ---------------------------------------------------------------------------
# Migrated from Server Script "V3 Workflow State Audit"
# (API: v3_workflow_state_audit).
#
# Finds V3 documents sitting in a workflow_state their workflow no longer
# defines -- usually left behind when a state is renamed or removed -- and
# resets the drafts among them to the first state. Submitted ones are only
# reported, never touched.
#
# Takes no arguments, so the body is entirely verbatim.
# ---------------------------------------------------------------------------
@frappe.whitelist()
def v3_workflow_state_audit():
	flows = frappe.get_all("Workflow", filters={"is_active": 1}, fields=["name", "document_type"])
	out = []
	for w in flows:
		wf = frappe.get_doc("Workflow", w.name)
		if not wf.document_type.endswith("V3"):
			continue
		valid = []
		for st in wf.states:
			valid.append(st.state)
		default_state = valid[0] if valid else None
		docs = frappe.get_all(wf.document_type, fields=["name", "workflow_state", "docstatus"], limit_page_length=0)
		for d in docs:
			if d.workflow_state and d.workflow_state not in valid:
				fixed = None
				if d.docstatus == 0 and default_state:
					frappe.db.set_value(wf.document_type, d.name, "workflow_state", default_state,
						update_modified=False)
					fixed = default_state
				out.append({"doctype": wf.document_type, "name": d.name,
							"was": d.workflow_state, "docstatus": d.docstatus, "now": fixed})
	frappe.response["message"] = {"stranded": out, "checked": len(flows)}


# ---------------------------------------------------------------------------
# Migrated from Server Script "V3 Clear Cache" (API: v3_clear_cache).
#
# Small operational helper: drops the cached Carrier Service meta so the
# Inbound Shipment V3 carrier/service pickers see edits without a full
# bench clear-cache.
#
# Takes no arguments, so the body is entirely verbatim.
# ---------------------------------------------------------------------------
@frappe.whitelist()
def v3_clear_cache():
	try:
		frappe.clear_cache(doctype="Carrier Service")
		frappe.response["message"]="OK"
	except Exception as e:
		frappe.response["message"]="ERR "+str(e)[:120]
