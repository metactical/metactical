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
    v3_reconcile          2 scripts  (see the warning on that function)
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


# NOTE: the "V3 Reconcile Receiving" API script defines its own v3_reconcile
# with a DIFFERENT body. That one is not interchangeable with this and stays
# local to the API module -- do not collapse the two.

def v3_reconcile(po3_name):
	# --- confirmation back-order rows ---
	soc = frappe.db.get_value("Supplier Order Confirmation V3",
		{"purchase_order_v3": po3_name, "docstatus": ("<", 2)}, "name")
	if soc:
		for b in frappe.get_all("Supplier Order Confirmation V3 Backorder",
				filters={"parent": soc}, fields=["name", "po3_item", "status"]):
			line = frappe.db.get_value("Purchase Order V3 Item", b.po3_item,
				["received_qty", "qty"], as_dict=True)
			if not line:
				continue
			got = float(line.received_qty or 0)
			upd = {"received_qty": got}
			if b.status in ("Open", "Shipped") and got >= float(line.qty or 0):
				upd["status"] = "Received"
			frappe.db.set_value("Supplier Order Confirmation V3 Backorder", b.name, upd)

	# --- shipments: flag what has landed, close any left In Transit ---
	for ins in frappe.get_all("Inbound Shipment V3",
			filters={"purchase_order_v3": po3_name, "docstatus": ("<", 2)},
			fields=["name", "workflow_state", "docstatus"]):
		d = frappe.get_doc("Inbound Shipment V3", ins.name)
		all_landed = True if d.items else False
		for it in d.items:
			if not it.po3_item:
				all_landed = False
				continue
			line = frappe.db.get_value("Purchase Order V3 Item", it.po3_item,
				["received_qty", "qty"], as_dict=True)
			if line and float(line.received_qty or 0) >= float(line.qty or 0):
				frappe.db.set_value("Inbound Shipment V3 Item", it.name, "received_flag", 1)
			else:
				all_landed = False
		if not all_landed:
			continue
		for b in d.boxes:
			frappe.db.set_value("Inbound Shipment V3 Box", b.name, "received", 1)
		if ins.docstatus == 0 and ins.workflow_state in ("Draft", "In Transit"):
			try:
				d.reload()
				d.workflow_state = "Received"
				d.docstatus = 1
				d.save()
				frappe.msgprint("Inbound Shipment " + ins.name
					+ " was still " + (ins.workflow_state or "Draft")
					+ " - marked <b>Received</b>, since its goods have all been receipted.")
			except Exception:
				pass
