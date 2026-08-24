# Copyright (c) 2026, Storebuilder Commerce Inc and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from metactical.procurement_v3.utils import F


class GoodsReceiptV3(Document):
	def validate(self):
		validate(self)


# ---------------------------------------------------------------------------
# Migrated from Server Script "GR3 Validate And Classify"
# (DocType Event / Before Save on Goods Receipt V3).
#
# Picks the shipment this count belongs to, lays out the expected lines, and
# classifies every counted row against what was expected -- Match / Short /
# Over / Wrong Variant / Wrong Item / Damaged / Unordered -- enforcing a
# disposition on anything that is not a clean match once counting is done.
#
# resolve_item and ident stay nested here ON PURPOSE. Supplier Order
# Confirmation V3 has functions of the same names with DIFFERENT bodies, so
# these two are NOT interchangeable and must never be hoisted into
# procurement_v3.utils.
# ---------------------------------------------------------------------------
def validate(doc):
	def resolve_item(val):
		if not val:
			return val
		if frappe.db.exists("Item", val):
			return val
		hit = frappe.db.get_value("Item", {"ifw_retailskusuffix": val}, "name")
		if not hit:
			hit = frappe.db.get_value("Item Barcode", {"barcode": val}, "parent")
		if not hit:
			hit = frappe.db.get_value("Item Supplier", {"supplier_part_no": val}, "parent")
		if not hit:
			frappe.throw("No item matches '" + str(val) + "' (tried item code, retail SKU, barcode, supplier SKU).")
		return hit

	def ident(item_code, supplier):
		return {
			"rs": frappe.db.get_value("Item", item_code, "ifw_retailskusuffix"),
			"bc": frappe.db.get_value("Item Barcode", {"parent": item_code}, "barcode"),
			"sp": frappe.db.get_value("Item Supplier", {"parent": item_code, "supplier": supplier}, "supplier_part_no")}


	po = frappe.get_doc("Purchase Order V3", doc.purchase_order_v3)
	if po.docstatus != 1:
		frappe.throw("Purchase Order V3 " + po.name + " is not submitted/approved yet.")
	rows = {}
	for r in po.items:
		rows[r.name] = r

	# ---- inbound shipment drives the receipt -------------------------
	# What is on the truck is a better expectation than what is open on the
	# order: the confirmation already told us the back-ordered balance is
	# not coming yet, and the shipment carries that forward.
	if not doc.inbound_shipment_v3:
		best_ship = None
		best_ship_key = None
		for cand in frappe.get_all("Inbound Shipment V3",
				filters={"purchase_order_v3": doc.purchase_order_v3,
						"workflow_state": ("in", ["In Transit", "Received"]),
						"docstatus": ("<", 2)},
				fields=["name", "ship_date", "creation"], limit_page_length=0):
			onboard = 0.0
			for si in frappe.get_all("Inbound Shipment V3 Item",
					filters={"parent": cand.name}, fields=["qty"], limit_page_length=0):
				onboard = onboard + float(si.qty or 0)
			taken = 0.0
			for prior in frappe.get_all("Goods Receipt V3",
					filters={"inbound_shipment_v3": cand.name, "docstatus": 1},
					fields=["name"], limit_page_length=0):
				for gi in frappe.get_all("Goods Receipt V3 Item",
						filters={"parent": prior.name}, fields=["received_qty"],
						limit_page_length=0):
					taken = taken + float(gi.received_qty or 0)
			if onboard - taken <= 0:
				continue                       # everything on it is already booked in
			# oldest first; a shipment with no ship date falls back to when it was made
			key = str(cand.ship_date or cand.creation)
			if best_ship_key is None or key < best_ship_key:
				best_ship_key = key
				best_ship = cand.name
		if best_ship:
			doc.inbound_shipment_v3 = best_ship

	if doc.inbound_shipment_v3:
		ship_po = frappe.db.get_value("Inbound Shipment V3", doc.inbound_shipment_v3,
			"purchase_order_v3")
		if ship_po and ship_po != doc.purchase_order_v3:
			frappe.throw("Inbound Shipment " + doc.inbound_shipment_v3 + " belongs to "
				+ str(ship_po) + ", not " + doc.purchase_order_v3 + ".")

	shipped_map = {}
	recv_on_ship = {}
	if doc.inbound_shipment_v3:
		for si in frappe.get_all("Inbound Shipment V3 Item",
				filters={"parent": doc.inbound_shipment_v3},
				fields=["po3_item", "qty"], limit_page_length=0):
			if si.po3_item:
				shipped_map[si.po3_item] = shipped_map.get(si.po3_item, 0) + float(si.qty or 0)

		# what earlier receipts already took off THIS shipment
		for p in frappe.get_all("Goods Receipt V3",
				filters={"inbound_shipment_v3": doc.inbound_shipment_v3, "docstatus": 1},
				fields=["name"], limit_page_length=0):
			if p.name == doc.name:
				continue
			for gi in frappe.get_all("Goods Receipt V3 Item", filters={"parent": p.name},
					fields=["po3_item", "received_qty"], limit_page_length=0):
				if gi.po3_item:
					recv_on_ship[gi.po3_item] = recv_on_ship.get(gi.po3_item, 0) + float(gi.received_qty or 0)


	# the order's ship-to warehouse is the sensible default; it only fills a
	# blank field, and the receiver can change it before posting
	if not doc.warehouse:
		doc.warehouse = frappe.db.get_value("Purchase Order V3", doc.purchase_order_v3,
			"set_warehouse")

	# drop the blank starter row the form adds, otherwise doc.items is
	# truthy and the prefill below never runs
	real_rows = []
	for d in doc.items:
		if d.received_item_code or d.po3_item:
			real_rows.append(d)
	if len(real_rows) != len(doc.items):
		doc.items = real_rows
		for i, d in enumerate(doc.items):
			d.idx = i + 1


	# empty grid -> lay out what we expect, with the count at ZERO.
	# Received is what someone physically counted, so it starts empty and is
	# counted up. Pre-filling it invites a receipt nobody actually checked.
	if not doc.items:
		for r in po.items:
			if r.line_status in ("Received", "Closed Short", "Cancelled", "Supplier Stock Out", "Discontinued"):
				continue
			if doc.inbound_shipment_v3:
				# only what this shipment says it is carrying
				out = shipped_map.get(r.name, 0) - recv_on_ship.get(r.name, 0)
			else:
				if r.line_status in ("Confirmed", "Partial", "Substituted"):
					base = float(r.confirmed_qty or 0)
				else:
					base = float(r.qty or 0)
				out = base - float(r.received_qty or 0)
			if out <= 0:
				continue
			d = doc.append("items", {})
			d.po3_item = r.name
			d.expected_item_code = r.item_code
			d.received_item_code = r.item_code
			d.expected_qty = out
			d.received_qty = 0
			d.accepted_qty = 0
			d.rejected_qty = 0

	# scanned / pasted rows: resolve identifiers, then link to an open PO line by item
	for d in doc.items:
		if d.received_item_code:
			d.received_item_code = resolve_item(d.received_item_code)
		if not d.po3_item and d.received_item_code:
			best = None
			for r in po.items:
				if r.item_code != d.received_item_code:
					continue
				if r.line_status in ("Received", "Closed Short", "Cancelled", "Supplier Stock Out", "Discontinued"):
					continue
				best = r.name
				break
			if best:
				d.po3_item = best
		ii = ident(d.received_item_code, doc.supplier)
		d.retail_sku_suffix = ii["rs"]
		d.barcode = ii["bc"]
		d.supplier_part_no = ii["sp"]

	strict = doc.workflow_state not in (None, "", "Draft", "Counting")
	var_count = 0
	any_rejected = False

	for d in doc.items:
		rec = F(d.received_qty)
		acc = F(d.accepted_qty)
		rej = F(d.rejected_qty)
		outstanding = 0.0
		if d.po3_item:
			r = rows.get(d.po3_item)
			if not r:
				frappe.throw("Row " + str(d.idx) + ": PO3 Line does not belong to " + po.name)
			d.expected_item_code = r.item_code
			# expectation basis: what the supplier said they would ship when we
			# have a confirmation; the ordered qty otherwise
			if doc.inbound_shipment_v3 and d.po3_item in shipped_map:
				# a shipment is a concrete promise about THIS delivery - expect
				# what is on the truck, not everything still open on the order
				outstanding = shipped_map[d.po3_item] - recv_on_ship.get(d.po3_item, 0)
				d.expected_qty = outstanding
				base = None
			elif r.line_status in ("Confirmed", "Partial", "Substituted"):
				base = F(r.confirmed_qty)
			elif r.line_status in ("Supplier Stock Out", "Discontinued", "Cancelled"):
				base = 0.0
			else:
				# Open or Back-ordered: the whole ordered qty is still due
				base = F(r.qty)
			if base is not None:
				outstanding = base - F(r.received_qty)
				d.expected_qty = outstanding
		else:
			d.expected_item_code = None
			d.expected_qty = 0

		if strict and abs(acc + rej - rec) > 0.000001:
			frappe.throw("Row " + str(d.idx) + " (" + (d.received_item_code or "") + "): Accepted ("
				+ str(acc) + ") + Rejected (" + str(rej) + ") must equal Received (" + str(rec)
				+ "). If part of this line had a different outcome, split it into two rows.")
		if rej > 0:
			any_rejected = True

		if not d.po3_item:
			vt = "Unordered"
		elif d.received_item_code and d.expected_item_code and d.received_item_code != d.expected_item_code:
			evo = frappe.db.get_value("Item", d.expected_item_code, "variant_of")
			rvo = frappe.db.get_value("Item", d.received_item_code, "variant_of")
			vt = "Wrong Variant" if (evo and rvo and evo == rvo) else "Wrong Item"
		elif rej > 0:
			vt = "Damaged"
		elif rec < outstanding:
			vt = "Short"
		elif rec > outstanding:
			vt = "Over"
		else:
			vt = "Match"
		d.variance_type = vt
		if vt in ("Short", "Over"):
			d.variance_qty = rec - outstanding
		elif vt == "Damaged":
			d.variance_qty = rej
		else:
			d.variance_qty = 0
		if vt != "Match":
			var_count += 1
			if strict and not d.disposition:
				frappe.throw("Row " + str(d.idx) + " (" + (d.received_item_code or "") + "): variance '"
					+ vt + "' needs a Disposition before this receipt can move on.")
		if strict and vt == "Match" and not d.disposition:
			d.disposition = "Accept"

	doc.has_variance = 1 if var_count else 0
	doc.variance_count = var_count

	if any_rejected and not doc.rejected_warehouse:
		doc.rejected_warehouse = frappe.db.get_single_value("Procurement Settings V3", "default_rejected_warehouse")
		if strict and not doc.rejected_warehouse:
			frappe.throw("This receipt has rejected quantity - set the Rejected Goods Warehouse (or a default in Procurement Settings V3).")

	# ---- counting it means it physically arrived --------------------
	if doc.inbound_shipment_v3 and doc.workflow_state not in (None, "", "Draft"):
		st = frappe.db.get_value("Inbound Shipment V3", doc.inbound_shipment_v3,
			["workflow_state", "docstatus"], as_dict=True)
		if st and st.docstatus == 0 and st.workflow_state in ("Draft", "In Transit"):
			try:
				ship = frappe.get_doc("Inbound Shipment V3", doc.inbound_shipment_v3)
				ship.workflow_state = "Received"
				ship.docstatus = 1
				ship.save()
				frappe.msgprint("Inbound Shipment " + doc.inbound_shipment_v3
					+ " marked <b>Received</b> - you are counting it, so it is here.")
			except Exception:
				pass

	# ---- counted more than the shipment says it carried ---------------
	# The variance code alone reads as a quantity, not as a problem. Say it in
	# words while there is still time to recount, and name the shipment so the
	# number can be checked against the packing list.
	if doc.inbound_shipment_v3 and doc.workflow_state in (None, "", "Draft", "Counting"):
		over_lines = []
		for d in doc.items:
			if d.variance_type == "Over" and F(d.variance_qty) > 0:
				over_lines.append((d.received_item_code or "?") + ": counted "
					+ str(F(d.received_qty)) + " but " + doc.inbound_shipment_v3
					+ " carries " + str(F(d.expected_qty)))
		if over_lines:
			frappe.msgprint("<b>Counted above what the shipment says it carried.</b><br>"
				+ "<br>".join(over_lines)
				+ "<br><br>If the supplier genuinely sent extra, carry on and give the "
				+ "line a Disposition. If the count is wrong, correct it now - after "
				+ "posting it becomes an over-receipt on the order.")
