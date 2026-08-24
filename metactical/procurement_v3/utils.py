# Copyright (c) 2026, Storebuilder Commerce Inc and contributors
# For license information, please see license.txt

"""Shared helpers for the Procurement V3 flow.

Each function here was defined -- byte-identically -- at the top of several of
the old V3 Server Scripts. They are hoisted into one module during the move to
code so the duplicates collapse without any change in behaviour:

    F                    17 scripts
    mirror_po3_status     8 scripts
    v3_may_close_native   2 scripts
    v3_open_bo            2 scripts
"""

import frappe


def F(x):
	return float(x or 0)


def mirror_po3_status(po3_name):
	row = frappe.db.get_value("Purchase Order V3", po3_name,
		["erp_purchase_order", "workflow_state"], as_dict=True)
	if row and row.erp_purchase_order:
		frappe.db.set_value("Purchase Order", row.erp_purchase_order,
			"custom_po3_status", row.workflow_state, update_modified=False)


def v3_may_close_native(po_name):
	st = frappe.db.get_value("Purchase Order", po_name,
		["status", "docstatus", "per_received", "per_billed"], as_dict=True)
	if not st or st.docstatus != 1:
		return {"ok": 0, "why": ""}
	if st.status in ("Closed", "Cancelled"):
		return {"ok": 0, "why": ""}
	if float(st.per_received or 0) <= 0:
		return {"ok": 1, "why": ""}          # nothing arrived, nothing to bill
	# per_billed is measured against ORDERED value, so a short-closed order
	# never reaches 100%. What matters is that everything which ARRIVED has
	# been invoiced.
	if float(st.per_billed or 0) + 0.001 >= float(st.per_received or 0):
		return {"ok": 1, "why": ""}
	return {"ok": 0, "why": "Native PO " + po_name + " left open: "
		+ str(round(float(st.per_received or 0), 1)) + "% received but only "
		+ str(round(float(st.per_billed or 0), 1)) + "% billed. ERPNext blocks a "
		+ "Purchase Invoice against a Closed order, so it must stay open until "
		+ "the supplier's invoice is posted."}


def v3_open_bo(po3_name):
	open_items = {}
	soc = frappe.db.get_value("Supplier Order Confirmation V3",
		{"purchase_order_v3": po3_name, "docstatus": ("<", 2)}, "name")
	if not soc:
		return open_items
	for b in frappe.get_all("Supplier Order Confirmation V3 Backorder",
			filters={"parent": soc}, fields=["po3_item", "status"], limit_page_length=0):
		if b.po3_item and b.status not in ("Received", "Cancelled"):
			open_items[b.po3_item] = 1
	return open_items
