# Copyright (c) 2026, Storebuilder Commerce Inc and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from metactical.procurement_v3.utils import (
	F,
	mirror_po3_status,
	v3_may_close_native,
	v3_open_bo,
	v3_reconcile,
)


class GoodsReceiptV3(Document):
	def validate(self):
		validate(self)

	def on_submit(self):
		post_to_po3(self)

	def before_cancel(self):
		cancel_guard(self)


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


# ---------------------------------------------------------------------------
# Migrated from Server Script "GR3 Post To PO3"
# (DocType Event / After Submit on Goods Receipt V3).
#
# Writes the counted quantities back onto the PO3 lines and re-derives each
# line status, reconciles the confirmation's backorders and any open shipments,
# rolls the order up to Partially Received / Received / Closed Short, and
# raises the native Purchase Receipt so stock actually moves.
# ---------------------------------------------------------------------------
def post_to_po3(doc):
	po = frappe.get_doc("Purchase Order V3", doc.purchase_order_v3)
	rows = {}
	for r in po.items:
		rows[r.name] = r

	open_bo_before = v3_open_bo(po.name)
	for d in doc.items:
		if not d.po3_item:
			continue
		# wrong-variant / wrong-item rows do NOT fulfil the ordered line -
		# the ordered item never arrived; those goods are handled by disposition + claim
		if d.received_item_code != d.expected_item_code:
			continue
		r = rows[d.po3_item]
		rec = F(r.received_qty) + F(d.received_qty)
		acc = F(r.accepted_qty) + F(d.accepted_qty)
		rej = F(r.rejected_qty) + F(d.rejected_qty)
		upd = {"received_qty": rec, "accepted_qty": acc, "rejected_qty": rej}
		if rec >= F(r.qty):
			upd["line_status"] = "Received"
			upd["over_qty"] = rec - F(r.qty)
			upd["short_qty"] = 0
			if r.backorder_status == "Open":
				upd["backorder_status"] = "Fulfilled"
		elif r.backorder_status == "Open" or d.po3_item in open_bo_before:
			# the confirmation still shows this balance outstanding, so the line
			# is not finished even if the mirrored flag says otherwise
			upd["line_status"] = "Back-ordered"
		else:
			upd["line_status"] = "Closed Short"
			upd["short_qty"] = F(r.qty) - rec
		frappe.db.set_value("Purchase Order V3 Item", d.po3_item, upd)

	# write receipts back onto the confirmation's Back Orders rows
	for d in doc.items:
		if not d.po3_item:
			continue
		line = frappe.db.get_value("Purchase Order V3 Item", d.po3_item,
			["line_status", "received_qty", "qty"], as_dict=True)
		if not line:
			continue
		for b in frappe.get_all("Supplier Order Confirmation V3 Backorder",
				filters={"po3_item": d.po3_item}, fields=["name", "status"]):
			upd = {"received_qty": F(line.received_qty)}
			if b.status in ("Open", "Shipped") and F(line.received_qty) >= F(line.qty):
				upd["status"] = "Received"
			frappe.db.set_value("Supplier Order Confirmation V3 Backorder", b.name, upd)

	open_bo_now = v3_open_bo(po.name)
	fresh = frappe.get_all("Purchase Order V3 Item", filters={"parent": po.name},
		fields=["name", "line_status"])
	all_terminal = bool(fresh)
	any_short = False
	for r in fresh:
		if r.line_status not in ("Received", "Closed Short", "Cancelled", "Supplier Stock Out", "Discontinued"):
			all_terminal = False
		elif r.name in open_bo_now:
			# goods are still owed on this line - nothing here is finished
			all_terminal = False
		if r.line_status in ("Closed Short", "Cancelled", "Supplier Stock Out", "Discontinued"):
			any_short = True

	close_native_after = 0
	hdr = {}
	if all_terminal:
		hdr["receipt_status"] = "Closed Short" if any_short else "Received"
		hdr["workflow_state"] = "Closed Short" if any_short else "Closed"
		open_grs = frappe.get_all("Goods Receipt V3",
			filters={"purchase_order_v3": po.name, "docstatus": 0,
					"name": ("!=", doc.name)}, fields=["name"], limit_page_length=1)
		if any_short and po.erp_purchase_order and not open_grs:
			# decided now, applied at the end - posting the receipt reopens the
			# native PO and recomputes its status, which would undo this
			close_native_after = 1
	else:
		hdr["receipt_status"] = "Partially Received"
		if po.workflow_state in ("Sent to Supplier", "Acknowledged"):
			hdr["workflow_state"] = "Partially Received"
	frappe.db.set_value("Purchase Order V3", po.name, hdr)

	frappe.db.set_value(doc.doctype, doc.name, {
		"posted_on": frappe.utils.now_datetime(), "posted_by": frappe.session.user})

	if frappe.db.get_single_value("Procurement Settings V3", "posting_enabled"):
		if po.erp_purchase_order:
			po_status = frappe.db.get_value("Purchase Order", po.erp_purchase_order, "status")
			if po_status == "Closed":
				try:
					frappe.get_doc("Purchase Order", po.erp_purchase_order).update_status("Submitted")
				except Exception:
					frappe.db.set_value("Purchase Order", po.erp_purchase_order, "status", "To Receive and Bill")
				frappe.msgprint("Native PO " + po.erp_purchase_order
					+ " was Closed - reopened so this receipt could post.")
			pr = frappe.new_doc("Purchase Receipt")
			pr.supplier = doc.supplier
			pr.company = po.company
			npo = frappe.db.get_value("Purchase Order", po.erp_purchase_order,
				["currency", "conversion_rate", "buying_price_list"], as_dict=True)
			pr.currency = npo.currency
			pr.conversion_rate = F(npo.conversion_rate) or 1
			pr.buying_price_list = npo.buying_price_list
			pr.purchase_order = po.erp_purchase_order
			for d in doc.items:
				if F(d.accepted_qty) <= 0 and F(d.rejected_qty) <= 0:
					continue
				row = pr.append("items", {})
				row.item_code = d.received_item_code
				row.qty = F(d.accepted_qty)
				row.rejected_qty = F(d.rejected_qty)
				row.warehouse = doc.warehouse
				row.rejected_warehouse = doc.rejected_warehouse
				if d.po3_item and d.received_item_code == d.expected_item_code:
					r = rows[d.po3_item]
					row.purchase_order = po.erp_purchase_order
					row.purchase_order_item = r.erp_po_item
					row.rate = F(r.rate)
				row.neb_source_doctype = doc.doctype
				row.neb_source_name = doc.name
				row.neb_source_detail = d.name
				row.neb_box_no = doc.box_no
			pr.insert()
			frappe.db.set_value(doc.doctype, doc.name, {"erp_purchase_receipt": pr.name})
			# The metactical app writes to the PR during insert, so the in-memory
			# copy is stale - reload before submitting or it fails on timestamp.
			submitted_pr = False
			pr_err = ""
			try:
				pr.reload()
				pr.submit()
				submitted_pr = True
			except Exception as e:
				pr_err = str(e)[:200]
			if not submitted_pr:
				try:
					fresh = frappe.get_doc("Purchase Receipt", pr.name)
					fresh.submit()
					submitted_pr = True
				except Exception as e:
					pr_err = str(e)[:200]
			if submitted_pr:
				frappe.msgprint("Purchase Receipt " + pr.name + " submitted - stock updated.")
			else:
				frappe.db.set_value(doc.doctype, doc.name, {"post_error": pr_err})
				frappe.msgprint("<b>Stock NOT updated.</b> Purchase Receipt " + pr.name
					+ " was created but could not be submitted:<br>" + pr_err
					+ "<br><br>Fix the cause, then use <b>Retry ERP Posting</b> on this Goods Receipt.")

	# a receipt supersedes a manual reopen - normal closing rules apply again
	frappe.db.set_value("Purchase Order V3", po.name, "manually_reopened", 0,
		update_modified=False)

	mirror_po3_status(po.name)

	v3_reconcile(po.name)

	# now that the receipt has posted, the order really is finished
	if close_native_after and po.erp_purchase_order:
		gate = v3_may_close_native(po.erp_purchase_order)
		if gate["ok"]:
			try:
				frappe.get_doc("Purchase Order", po.erp_purchase_order).update_status("Closed")
			except Exception:
				frappe.db.set_value("Purchase Order", po.erp_purchase_order, "status", "Closed")
		elif gate["why"]:
			frappe.msgprint(gate["why"])


# ---------------------------------------------------------------------------
# Migrated from Server Script "GR3 Cancel Guard"
# (DocType Event / Before Cancel on Goods Receipt V3).
#
# While the native Purchase Receipt is still submitted the stock it moved is
# on hand, so that has to be cancelled first -- which rolls the quantities back
# off the order on its own.
# ---------------------------------------------------------------------------
def cancel_guard(doc):
	if doc.erp_purchase_receipt:
		pr = frappe.db.get_value("Purchase Receipt", doc.erp_purchase_receipt,
			["docstatus", "name"], as_dict=True)
		if pr and pr.docstatus == 1:
			frappe.throw("<b>" + doc.name + " cannot be cancelled yet.</b><br><br>"
				+ "Purchase Receipt <b>" + pr.name + "</b> is still submitted, so the "
				+ "stock it moved is still on hand.<br><br>Cancel " + pr.name
				+ " first - that rolls the quantities back off the order "
				+ "automatically - then cancel this receipt.")


# ---------------------------------------------------------------------------
# Migrated from Server Script "V3 GR3 Scan Map" (API: v3_gr3_scan_map).
#
# Builds the barcode/SKU -> item_code lookup the receipt form scans against:
# item code, retail SKU suffix, every Item Barcode, and this supplier's part
# numbers, all upper-cased. Called once per receipt and cached client-side.
#
# No alias in hooks.py: the only caller is goods_receipt_v3.js, repointed to
# this dotted path.
# ---------------------------------------------------------------------------
@frappe.whitelist()
def v3_gr3_scan_map(po3=None):
	supplier = frappe.db.get_value("Purchase Order V3", po3, "supplier")
	out = {}
	names = {}
	for r in frappe.get_all("Purchase Order V3 Item", filters={"parent": po3},
			fields=["item_code"], limit_page_length=0):
		ic = r.item_code
		if not ic or ic in names:
			continue
		nm = frappe.db.get_value("Item", ic, ["item_name", "ifw_retailskusuffix"], as_dict=True)
		names[ic] = (nm.item_name if nm else ic) or ic
		out[ic.upper()] = ic
		if nm and nm.ifw_retailskusuffix:
			out[str(nm.ifw_retailskusuffix).upper()] = ic
		for b in frappe.get_all("Item Barcode", filters={"parent": ic},
				fields=["barcode"], limit_page_length=0):
			if b.barcode:
				out[str(b.barcode).upper()] = ic
		for sp in frappe.get_all("Item Supplier",
				filters={"parent": ic, "supplier": supplier},
				fields=["supplier_part_no"], limit_page_length=0):
			if sp.supplier_part_no:
				out[str(sp.supplier_part_no).upper()] = ic
	frappe.response["message"] = {"map": out, "names": names}


# ---------------------------------------------------------------------------
# Migrated from Server Script "V3 GR3 Prefill Preview"
# (API: v3_gr3_prefill_preview).
#
# Works out which lines a new receipt should show and what is outstanding on
# each, so the form can lay the grid out before anything is saved. Counts are
# always returned at zero -- the server re-derives them on save.
#
# No alias in hooks.py: the only caller is goods_receipt_v3.js, repointed here.
# ---------------------------------------------------------------------------
@frappe.whitelist()
def v3_gr3_prefill_preview(po3=None, shipment=None):
	po = frappe.get_doc("Purchase Order V3", po3)

	# pick the shipment exactly as GR3 Validate And Classify does
	ship = shipment
	if not ship:
		best = None
		best_key = None
		for cand in frappe.get_all("Inbound Shipment V3",
				filters={"purchase_order_v3": po3,
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
				continue
			key = str(cand.ship_date or cand.creation)
			if best_key is None or key < best_key:
				best_key = key
				best = cand.name
		ship = best

	shipped_map = {}
	recv_on_ship = {}
	if ship:
		for si in frappe.get_all("Inbound Shipment V3 Item", filters={"parent": ship},
				fields=["po3_item", "qty"], limit_page_length=0):
			if si.po3_item:
				shipped_map[si.po3_item] = shipped_map.get(si.po3_item, 0) + float(si.qty or 0)
		for p in frappe.get_all("Goods Receipt V3",
				filters={"inbound_shipment_v3": ship, "docstatus": 1},
				fields=["name"], limit_page_length=0):
			for gi in frappe.get_all("Goods Receipt V3 Item", filters={"parent": p.name},
					fields=["po3_item", "received_qty"], limit_page_length=0):
				if gi.po3_item:
					recv_on_ship[gi.po3_item] = recv_on_ship.get(gi.po3_item, 0) + float(gi.received_qty or 0)

	rows = []
	for r in po.items:
		if r.line_status in ("Received", "Closed Short", "Cancelled", "Supplier Stock Out", "Discontinued"):
			continue
		if ship:
			out = shipped_map.get(r.name, 0) - recv_on_ship.get(r.name, 0)
		else:
			if r.line_status in ("Confirmed", "Partial", "Substituted"):
				base = float(r.confirmed_qty or 0)
			else:
				base = float(r.qty or 0)
			out = base - float(r.received_qty or 0)
		if out <= 0:
			continue
		rows.append({"po3_item": r.name, "expected_item_code": r.item_code,
			"received_item_code": r.item_code, "expected_qty": out,
			"retail_sku_suffix": r.retail_sku_suffix})

	frappe.response["message"] = {"shipment": ship, "warehouse": po.set_warehouse, "rows": rows}


# ---------------------------------------------------------------------------
# Migrated from Server Script "V3 Retry GR3 Posting"
# (API: v3_retry_gr3_posting).
#
# Recovery for a posted Goods Receipt V3 whose native Purchase Receipt never
# made it: submits an existing draft PR, or builds and submits a new one.
# Backs the "Retry ERP Posting" button.
#
# No alias in hooks.py: the only caller is goods_receipt_v3.js, repointed here.
# ---------------------------------------------------------------------------
@frappe.whitelist()
def v3_retry_gr3_posting(gr3=None):
	# v3_retry_gr3_posting?gr3=GR3-YYYY-NNNNN
	# Submits the draft PR a Goods Receipt already created, or creates one if the
	# earlier attempt never got that far. Safe to call repeatedly.
	name = gr3
	if not name:
		frappe.throw("pass gr3=<name>")
	doc = frappe.get_doc("Goods Receipt V3", name)
	if doc.docstatus != 1 or doc.workflow_state != "Posted":
		frappe.throw(name + " is not Posted - nothing to retry.")

	if doc.erp_purchase_receipt and frappe.db.exists("Purchase Receipt", doc.erp_purchase_receipt):
		pr = frappe.get_doc("Purchase Receipt", doc.erp_purchase_receipt)
		if pr.docstatus == 1:
			frappe.db.set_value(doc.doctype, doc.name, {"post_error": None})
			frappe.response["message"] = {"status": "already submitted", "pr": pr.name}
		elif pr.docstatus == 2:
			frappe.throw("Purchase Receipt " + pr.name + " was cancelled. Amend it in ERP, or cancel this Goods Receipt and re-receive.")
		else:
			try:
				pr.submit()
				frappe.db.set_value(doc.doctype, doc.name, {"post_error": None})
				frappe.response["message"] = {"status": "submitted", "pr": pr.name}
			except Exception as e:
				msg = str(e)[:300]
				frappe.db.set_value(doc.doctype, doc.name, {"post_error": msg})
				frappe.throw("Still could not submit " + pr.name + ": " + msg)
	else:
		if not frappe.db.get_single_value("Procurement Settings V3", "posting_enabled"):
			frappe.throw("Posting to native ERP is disabled in Procurement Settings V3.")
		po = frappe.get_doc("Purchase Order V3", doc.purchase_order_v3)
		if not po.erp_purchase_order:
			frappe.throw(po.name + " has no native Purchase Order yet.")
		rows = {}
		for r in po.items:
			rows[r.name] = r
		npo = frappe.db.get_value("Purchase Order", po.erp_purchase_order,
			["currency", "conversion_rate", "buying_price_list"], as_dict=True)
		po_status = frappe.db.get_value("Purchase Order", po.erp_purchase_order, "status")
		if po_status == "Closed":
			try:
				frappe.get_doc("Purchase Order", po.erp_purchase_order).update_status("Submitted")
			except Exception:
				frappe.db.set_value("Purchase Order", po.erp_purchase_order, "status", "To Receive and Bill")
			frappe.msgprint("Native PO " + po.erp_purchase_order
				+ " was Closed - reopened so this receipt could post.")
		pr = frappe.new_doc("Purchase Receipt")
		pr.supplier = doc.supplier
		pr.company = po.company
		pr.currency = npo.currency
		pr.conversion_rate = F(npo.conversion_rate) or 1
		pr.buying_price_list = npo.buying_price_list
		pr.purchase_order = po.erp_purchase_order
		for d in doc.items:
			if F(d.accepted_qty) <= 0 and F(d.rejected_qty) <= 0:
				continue
			row = pr.append("items", {})
			row.item_code = d.received_item_code
			row.qty = F(d.accepted_qty)
			row.rejected_qty = F(d.rejected_qty)
			row.warehouse = doc.warehouse
			row.rejected_warehouse = doc.rejected_warehouse
			if d.po3_item and d.received_item_code == d.expected_item_code:
				r = rows.get(d.po3_item)
				if r:
					row.purchase_order = po.erp_purchase_order
					row.purchase_order_item = r.erp_po_item
					row.rate = F(r.rate)
			row.neb_source_doctype = doc.doctype
			row.neb_source_name = doc.name
			row.neb_source_detail = d.name
			row.neb_box_no = doc.box_no
		pr.insert()
		frappe.db.set_value(doc.doctype, doc.name, {"erp_purchase_receipt": pr.name})
		try:
			pr.reload()
			pr.submit()
			frappe.db.set_value(doc.doctype, doc.name, {"post_error": None})
			frappe.response["message"] = {"status": "created and submitted", "pr": pr.name}
		except Exception as e:
			msg = str(e)[:300]
			frappe.db.set_value(doc.doctype, doc.name, {"post_error": msg})
			frappe.throw("Created " + pr.name + " but could not submit it: " + msg)
