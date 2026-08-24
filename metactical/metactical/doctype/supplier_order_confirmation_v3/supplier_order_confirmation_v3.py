# Copyright (c) 2026, Storebuilder Commerce Inc and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from metactical.procurement_v3.utils import F


class SupplierOrderConfirmationV3(Document):
	def validate(self):
		validate(self)


# ---------------------------------------------------------------------------
# Migrated from Server Script "SOC3 Validate"
# (DocType Event / Before Save on Supplier Order Confirmation V3).
#
# Pulls the confirmable lines off the parent PO3, resolves supplier item
# identifiers, works out what each line still has outstanding once other
# confirmations are accounted for, and keeps the backorder rows in step.
#
# resolve_item / ident / balance_qty / outstanding stay nested here: GR3 has
# its own resolve_item and ident with different bodies, so these are NOT
# interchangeable and must not be hoisted into procurement_v3.utils.
# ---------------------------------------------------------------------------
def validate(doc):
	def resolve_item(val):
		if frappe.db.exists("Item", val):
			return val
		hit = frappe.db.get_value("Item", {"ifw_retailskusuffix": val}, "name")
		if not hit:
			hit = frappe.db.get_value("Item Barcode", {"barcode": val}, "parent")
		return hit

	def ident(item_code, supplier):
		return {
			"rs": frappe.db.get_value("Item", item_code, "ifw_retailskusuffix"),
			"bc": frappe.db.get_value("Item Barcode", {"barcode": ("!=", "")}, "barcode") if False else frappe.db.get_value("Item Barcode", {"parent": item_code}, "barcode"),
			"sp": frappe.db.get_value("Item Supplier", {"parent": item_code, "supplier": supplier}, "supplier_part_no")}

	if doc.ai_parsed and not doc.source_document:
		frappe.throw("AI-parsed confirmations must have the source document attached.")

	po = frappe.get_doc("Purchase Order V3", doc.purchase_order_v3)
	if po.docstatus != 1:
		frappe.throw("Purchase Order V3 " + po.name + " is not submitted/approved yet.")

	rows = {}
	for r in po.items:
		rows[r.name] = r

	# ONE confirmation per PO. Back-order balances live on this document's
	# Back Orders tab; later supplier documents go on the Documents tab.
	if doc.is_new() and not doc.supersedes:
		prior = frappe.get_all("Supplier Order Confirmation V3",
			filters={"purchase_order_v3": doc.purchase_order_v3, "name": ("!=", doc.name), "docstatus": ("<", 2)},
			fields=["name"], limit_page_length=1)
		if prior:
			frappe.throw(po.name + " is already confirmed on " + prior[0].name
				+ ". Track back-order balances on its Back Orders tab and attach later supplier "
				+ "documents on its Documents tab. To replace it outright, set Supersedes.")

	# Which PO3 lines are already spoken for by another confirmation?
	# A back-ordered line is deliberately re-openable: that is how the supplier
	# confirms the balance shipment later.
	claimed = {}
	for other in frappe.get_all("Supplier Order Confirmation V3",
			filters={"purchase_order_v3": po.name, "name": ("!=", doc.name), "docstatus": ("<", 2)},
			fields=["name"]):
		# the document we are replacing does not block us
		if doc.supersedes and other.name == doc.supersedes:
			continue
		for ln in frappe.get_all("Supplier Order Confirmation V3 Item",
				filters={"parent": other.name}, fields=["po3_item"]):
			claimed[ln.po3_item] = other.name

	TERMINAL = ("Received", "Closed Short", "Cancelled", "Supplier Stock Out", "Discontinued")

	# helpers cannot see script-level locals in this sandbox - pass everything in
	def balance_qty(r, claimed_map):
		# a re-opened back-ordered line offers only what has not been promised yet
		if r.line_status == "Back-ordered" and r.name in claimed_map:
			done = float(r.confirmed_qty or 0)
			if float(r.received_qty or 0) > done:
				done = float(r.received_qty or 0)
			return float(r.qty or 0) - done
		return float(r.qty or 0) - float(r.received_qty or 0)

	def outstanding(r, claimed_map):
		if r.line_status in ("Received", "Closed Short", "Cancelled", "Supplier Stock Out", "Discontinued"):
			return False
		if r.name in claimed_map and r.line_status != "Back-ordered":
			return False
		return True

	# empty grid -> pull only what is still outstanding
	if not doc.items:
		for r in po.items:
			if not outstanding(r, claimed):
				continue
			d = doc.append("items", {})
			d.po3_item = r.name
			d.item_code = r.item_code
			d.ordered_qty = balance_qty(r, claimed)
			d.confirmed_qty = d.ordered_qty
			d.line_status = "Confirmed"
			d.confirmed_rate = r.rate
		if not doc.items:
			frappe.throw("Nothing outstanding on " + po.name
				+ " - every line is already received, closed, or covered by another confirmation.")

	# pasted / scanned rows: resolve item then match an outstanding line
	used = {}
	for d in doc.items:
		if d.po3_item:
			used[d.po3_item] = 1
	for d in doc.items:
		if not d.po3_item:
			code = resolve_item(str(d.item_code or "").strip())
			if not code:
				frappe.throw("Row " + str(d.idx) + ": no item matches '" + str(d.item_code) + "'.")
			d.item_code = code
			match = None
			for r in po.items:
				if r.item_code == code and r.name not in used and outstanding(r, claimed):
					match = r.name
					break
			if not match:
				frappe.throw("Row " + str(d.idx) + ": " + code + " is not outstanding on " + po.name
					+ " (already received, closed, or on another confirmation).")
			d.po3_item = match
			used[match] = 1
			if not d.line_status:
				d.line_status = "Confirmed"

	others = frappe.get_all("Supplier Order Confirmation V3",
		filters={"purchase_order_v3": doc.purchase_order_v3, "name": ("!=", doc.name), "docstatus": ("<", 2)},
		fields=["name"])
	doc.revision_no = len(others) + 1

	for d in doc.items:
		if d.po3_item not in rows:
			frappe.throw("Row " + str(d.idx) + ": PO3 Line does not belong to " + po.name)
		r = rows[d.po3_item]

		if r.line_status in TERMINAL:
			frappe.throw("Row " + str(d.idx) + " (" + (r.item_code or "")
				+ "): that PO line is already '" + r.line_status + "' - it cannot be confirmed again.")
		if d.po3_item in claimed and r.line_status != "Back-ordered":
			frappe.throw("Row " + str(d.idx) + " (" + (r.item_code or "")
				+ "): already covered by " + claimed[d.po3_item] + ". Remove the row, or supersede that confirmation.")

		d.item_code = r.item_code
		d.ordered_qty = balance_qty(r, claimed)
		d.item_name = frappe.db.get_value("Item", d.item_code, "item_name")
		ii = ident(d.item_code, doc.supplier)
		d.retail_sku_suffix = ii["rs"]
		d.barcode = ii["bc"]
		d.supplier_part_no = ii["sp"]

		q = F(d.confirmed_qty)
		o = F(d.ordered_qty)
		s = d.line_status
		if s in ("Supplier Stock Out", "Discontinued", "Cancelled by Supplier") and q != 0:
			frappe.throw("Row " + str(d.idx) + " (" + (d.item_code or "") + "): status '" + s
				+ "' requires Confirmed Qty = 0, got " + str(q))
		if s == "Confirmed" and q != o:
			frappe.throw("Row " + str(d.idx) + " (" + (d.item_code or "")
				+ "): 'Confirmed' means the full outstanding qty (" + str(o) + "), got " + str(q)
				+ ". Use a 'Partial - ...' status for less.")
		if s in ("Partial - Balance Cancelled", "Partial - Balance Back-ordered") and not (0 < q < o):
			frappe.throw("Row " + str(d.idx) + " (" + (d.item_code or "") + "): '" + s
				+ "' requires 0 < Confirmed Qty < " + str(o))
		if s == "Back-ordered" and q != 0:
			frappe.throw("Row " + str(d.idx) + " (" + (d.item_code or "")
				+ "): 'Back-ordered' means nothing ships now, so Confirmed Qty must be 0 (the full "
				+ str(o) + " follows later). Use 'Partial - Balance Back-ordered' if some of it ships now.")
		if s == "Substituted" and not d.substitute_item_code:
			frappe.throw("Row " + str(d.idx) + " (" + (d.item_code or "") + "): 'Substituted' requires the Substitute Item.")
		if d.confirmed_rate and F(r.rate):
			d.rate_variance_pct = (F(d.confirmed_rate) - F(r.rate)) / F(r.rate) * 100.0

	# --- rebuild the Back Orders tab from the lines ---
	keep = {}
	for b in (doc.backorders or []):
		keep[b.po3_item] = b
	doc.backorders = []
	for d in doc.items:
		if d.line_status not in ("Back-ordered", "Partial - Balance Back-ordered"):
			continue
		if d.line_status == "Back-ordered":
			now_qty = 0.0
			bal = F(d.ordered_qty)
		else:
			now_qty = F(d.confirmed_qty)
			bal = F(d.ordered_qty) - F(d.confirmed_qty)
		if bal <= 0:
			continue
		b = doc.append("backorders", {})
		b.po3_item = d.po3_item
		b.item_code = d.item_code
		nm = frappe.db.get_value("Item", d.item_code, "item_name")
		b.item_display = (d.item_code + ": " + nm) if nm else d.item_code
		b.item_name = nm
		b.ordered_qty = F(d.ordered_qty)
		b.shipping_now = now_qty
		b.balance_qty = bal
		b.received_qty = F(r.received_qty)
		old = keep.get(d.po3_item)
		b.eta = (old.eta if old and old.eta else d.backorder_eta)
		b.status = (old.status if old else "Open")
		b.cancel_reason = (old.cancel_reason if old else None)
		b.remarks = (old.remarks if old else None)
