# Copyright (c) 2026, Storebuilder Commerce Inc and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from metactical.procurement_v3.taxes import copy_taxes_to_native
from metactical.procurement_v3.utils import (
	F,
	item_supplier_part_no,
	item_unavailable,
	mirror_po3_status,
	throw_unavailable,
	v3_may_close_native,
	v3_open_bo,
	v3_reconcile,
)


class PurchaseReceiptV3(Document):
	def validate(self):
		validate(self)

	def on_update(self):
		sync_native_pr(self)

	def on_submit(self):
		post_to_po3(self)

	def before_cancel(self):
		cancel_guard(self)

	def on_cancel(self):
		delete_native_pr(self)

	def on_trash(self):
		delete_native_pr(self)


# ---------------------------------------------------------------------------
# What the supplier said they would send -- the receipt counts against the
# Supplier Order Confirmation V3, not the PO3. The PO stays what was ordered;
# the confirmation is what is coming: substitutes in place of the ordered
# item, new items, increased quantities, and the confirmed rate.
#
# A PO3 has one live confirmation (a later one supersedes it). Each of its
# lines is one expected line: the substitute when Substituted, its confirmed
# qty plus any back-ordered balance, less what has already been received.
# ---------------------------------------------------------------------------
# The reject reason for a short line whose balance is still coming: the line
# stays open and the next receipt expects the rest. Any other reason on a short
# line closes it.
PARTIALLY_RECEIVED = "Partially Received"


def live_confirmation(po3_name):
	socs = frappe.get_all("Supplier Order Confirmation V3",
		filters={"purchase_order_v3": po3_name, "docstatus": 1},
		fields=["name", "supersedes"], order_by="creation desc")
	superseded = {s.supersedes for s in socs if s.supersedes}
	for s in socs:
		if s.name not in superseded:
			return s.name
	return None


def soc3_expected(po, exclude=None):
	"""{soc3_item: line} for the PO3's live confirmation. Throws if there is none."""
	soc = live_confirmation(po.name)
	if not soc:
		frappe.throw("Submit the Supplier Order Confirmation V3 for " + po.name
			+ " first - the receipt is counted against what the supplier confirmed.")
	rows = {r.name: r for r in po.items}
	balance = {}
	for b in frappe.get_all("Supplier Order Confirmation V3 Backorder",
			filters={"parent": soc, "status": ("!=", "Cancelled")},
			fields=["po3_item", "balance_qty"]):
		balance[b.po3_item] = balance.get(b.po3_item, 0) + F(b.balance_qty)

	# goods the PO3 line does not track (substitutes, new items) are counted
	# off the earlier receipts made against the confirmation line
	got_on_soc = {}
	for gi in frappe.db.sql("""select gi.soc3_item, gi.received_qty from `tabPurchase Receipt V3 Item` gi
			join `tabPurchase Receipt V3` g on g.name = gi.parent
			where g.docstatus = 1 and g.purchase_order_v3 = %s and g.name != %s
			and ifnull(gi.soc3_item, '') != '' and gi.received_item_code = gi.expected_item_code""",
			(po.name, exclude or ""), as_dict=True):
		got_on_soc[gi.soc3_item] = got_on_soc.get(gi.soc3_item, 0) + F(gi.received_qty)

	# a line that came in short is finished, unless the receiver said the rest
	# is still coming (Partially Received) - or it has an open back-order, which
	# stays expected until it is received or cancelled on the Back Orders tab
	open_bo = v3_open_bo(po.name)
	closed_on_soc = set(frappe.db.sql_list("""select distinct gi.soc3_item
			from `tabPurchase Receipt V3 Item` gi join `tabPurchase Receipt V3` g on g.name = gi.parent
			where g.docstatus = 1 and g.purchase_order_v3 = %s and g.name != %s
			and ifnull(gi.soc3_item, '') != '' and gi.variance_type = 'Short'
			and ifnull(gi.reject_reason, '') != %s""", (po.name, exclude or "", PARTIALLY_RECEIVED)))

	out = {}
	for ln in frappe.get_all("Supplier Order Confirmation V3 Item", filters={"parent": soc},
			fields=["name", "po3_item", "item_code", "substitute_item_code", "line_status",
				"confirmed_qty", "confirmed_rate"], order_by="idx"):
		item = ln.substitute_item_code if ln.line_status == "Substituted" else ln.item_code
		r = rows.get(ln.po3_item)
		qty = F(ln.confirmed_qty)
		# a back-order cancelled on the PO3 line is not coming either
		if item == ln.item_code and not (r and r.backorder_status == "Cancelled"):
			qty += balance.get(ln.po3_item, 0)
		# the PO3 line already counts every receipt of its own item, including
		# ones from before receipts were linked to the confirmation
		got = F(r.received_qty) if r and r.item_code == item else got_on_soc.get(ln.name, 0)
		out[ln.name] = frappe._dict(soc3_item=ln.name, po3_item=ln.po3_item or None, item_code=item,
			qty=qty, received=got, rate=F(ln.confirmed_rate) or (F(r.rate) if r else 0),
			closed=bool(r and r.item_code == item and r.line_status in ("Closed Short", "Cancelled"))
				or (ln.name in closed_on_soc and ln.po3_item not in open_bo))
	return out


# Where a shipment is being received, it says what is on the truck: lines are
# keyed by their PO3 line, or by item for new items that have none.
def shipment_key(po3_item, item_code):
	return po3_item or ("item", item_code)


def shipment_balance(ship, exclude=None):
	shipped, taken = {}, {}
	if not ship:
		return shipped, taken
	for si in frappe.get_all("Inbound Shipment V3 Item", filters={"parent": ship},
			fields=["po3_item", "item_code", "qty"], limit_page_length=0):
		k = shipment_key(si.po3_item, si.item_code)
		shipped[k] = shipped.get(k, 0) + F(si.qty)
	for p in frappe.get_all("Purchase Receipt V3",
			filters={"inbound_shipment_v3": ship, "docstatus": 1, "name": ("!=", exclude or "")},
			fields=["name"], limit_page_length=0):
		for gi in frappe.get_all("Purchase Receipt V3 Item", filters={"parent": p.name},
				fields=["po3_item", "received_item_code", "received_qty"], limit_page_length=0):
			k = shipment_key(gi.po3_item, gi.received_item_code)
			taken[k] = taken.get(k, 0) + F(gi.received_qty)
	return shipped, taken


def outstanding_on(ln, ship, shipped, taken):
	"""What is still to come on a confirmation line -- on this shipment when there is one."""
	k = shipment_key(ln.po3_item, ln.item_code)
	if ship and k in shipped:
		return shipped[k] - taken.get(k, 0)
	return ln.qty - ln.received


def expected_rows(po, ship, exclude=None):
	"""The grid a new receipt starts from: every confirmation line with something still to come."""
	expected = soc3_expected(po, exclude)
	shipped, taken = shipment_balance(ship, exclude)
	out = []
	for ln in expected.values():
		if ln.closed:
			continue
		if ship and shipment_key(ln.po3_item, ln.item_code) not in shipped:
			# only what this shipment says it is carrying
			continue
		qty = outstanding_on(ln, ship, shipped, taken)
		if qty > 0:
			out.append(frappe._dict(soc3_item=ln.soc3_item, po3_item=ln.po3_item,
				item_code=ln.item_code, expected_qty=qty))
	return out


def pick_shipment(po, exclude=None):
	"""The shipment a new receipt is most likely counting: the oldest one that still
	has something expected on it. A shipment whose leftovers were closed short has
	nothing more to bring, so it must not keep getting picked over a later one."""
	best, best_key = None, None
	for cand in frappe.get_all("Inbound Shipment V3",
			filters={"purchase_order_v3": po.name,
					"workflow_state": ("in", ["In Transit", "Received"]),
					"docstatus": ("<", 2)},
			fields=["name", "ship_date", "creation"], limit_page_length=0):
		if not expected_rows(po, cand.name, exclude):
			continue
		# oldest first; a shipment with no ship date falls back to when it was made,
		# and on the same ship date the one made first, so the pick does not depend on row order
		key = (str(cand.ship_date or cand.creation), str(cand.creation))
		if best_key is None or key < best_key:
			best_key, best = key, cand.name
	return best


# ---------------------------------------------------------------------------
# Migrated from Server Script "GR3 Validate And Classify"
# (DocType Event / Before Save on Purchase Receipt V3).
#
# Picks the shipment this count belongs to, lays out the expected lines from
# the supplier's confirmation (soc3_expected), and classifies every counted
# row against what was expected -- Match / Short /
# Over / Wrong Variant / Wrong Item / Damaged / Unordered -- enforcing a
# Reject Reason on every Short line once counting is done.
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
			# the same fallbacks PO3 and SOC3 use, so the receipt shows the
			# supplier SKU the order line does
			"sp": item_supplier_part_no(item_code, supplier)}


	po = frappe.get_doc("Purchase Order V3", doc.purchase_order_v3)
	if po.docstatus != 1:
		frappe.throw("Purchase Order V3 " + po.name + " is not submitted/approved yet.")
	rows = {}
	for r in po.items:
		rows[r.name] = r
	expected = soc3_expected(po, doc.name)

	# ---- inbound shipment drives the receipt -------------------------
	# What is on the truck is a better expectation than what is open on the
	# order: the confirmation already told us the back-ordered balance is
	# not coming yet, and the shipment carries that forward.
	if not doc.inbound_shipment_v3:
		best_ship = pick_shipment(po, doc.name)
		if best_ship:
			doc.inbound_shipment_v3 = best_ship

	if doc.inbound_shipment_v3:
		ship_po = frappe.db.get_value("Inbound Shipment V3", doc.inbound_shipment_v3,
			"purchase_order_v3")
		if ship_po and ship_po != doc.purchase_order_v3:
			frappe.throw("Inbound Shipment " + doc.inbound_shipment_v3 + " belongs to "
				+ str(ship_po) + ", not " + doc.purchase_order_v3 + ".")

	shipped, taken = shipment_balance(doc.inbound_shipment_v3, doc.name)


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
		for x in expected_rows(po, doc.inbound_shipment_v3, doc.name):
			d = doc.append("items", {})
			d.soc3_item = x.soc3_item
			d.po3_item = x.po3_item
			d.expected_item_code = x.item_code
			d.received_item_code = x.item_code
			d.expected_qty = x.expected_qty
			d.received_qty = 0
			d.accepted_qty = 0
			d.rejected_qty = 0
		if not doc.items:
			frappe.throw("Nothing is left to receive on " + po.name + (" from " + doc.inbound_shipment_v3
				if doc.inbound_shipment_v3 else "") + ": everything the supplier confirmed has been "
				"received, closed short or cancelled.")

	# scanned / pasted rows: resolve identifiers, then link to the confirmation
	# line expecting that item -- or, failing that, an open PO line for it
	for d in doc.items:
		if d.received_item_code:
			d.received_item_code = resolve_item(d.received_item_code)
		if not d.soc3_item and d.received_item_code:
			hits = [ln for ln in expected.values() if ln.item_code == d.received_item_code
				and (not d.po3_item or ln.po3_item == d.po3_item)]
			hit = next((ln for ln in hits if ln.qty > ln.received), hits[0] if hits else None)
			if hit:
				d.soc3_item = hit.soc3_item
				d.po3_item = hit.po3_item
		if not d.po3_item and not d.soc3_item and d.received_item_code:
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

	# a discontinued or disabled item can't be received. Only rows that actually
	# counted something: lines laid out from the order at zero are left alone,
	# so a receipt can still be opened against an order that has one
	throw_unavailable([(d.idx, d.received_item_code, why) for d in doc.items
		if F(d.received_qty) or F(d.accepted_qty) or F(d.rejected_qty)
		for why in [item_unavailable(d.received_item_code)] if why], "received")

	strict = doc.workflow_state not in (None, "", "Draft", "Counting")
	var_count = 0
	any_rejected = False

	for d in doc.items:
		rec = F(d.received_qty)
		acc = F(d.accepted_qty)
		rej = F(d.rejected_qty)
		outstanding = 0.0
		if d.soc3_item:
			ln = expected.get(d.soc3_item)
			if not ln:
				frappe.throw("Row " + str(d.idx) + ": SOC3 Line does not belong to the confirmation for "
					+ po.name + ".")
			d.po3_item = ln.po3_item
			d.expected_item_code = ln.item_code
			# a shipment is a concrete promise about THIS delivery - expect what
			# is on the truck, not everything still to come on the confirmation
			outstanding = outstanding_on(ln, doc.inbound_shipment_v3, shipped, taken)
			d.expected_qty = outstanding
		elif d.po3_item:
			# on the order, but the supplier did not confirm sending it
			r = rows.get(d.po3_item)
			if not r:
				frappe.throw("Row " + str(d.idx) + ": PO3 Line does not belong to " + po.name)
			d.expected_item_code = r.item_code
			d.expected_qty = 0
		else:
			d.expected_item_code = None
			d.expected_qty = 0

		if strict and abs(acc + rej - rec) > 0.000001:
			frappe.throw("Row " + str(d.idx) + " (" + (d.received_item_code or "") + "): Accepted ("
				+ str(acc) + ") + Rejected (" + str(rej) + ") must equal Received (" + str(rec)
				+ "). If part of this line had a different outcome, split it into two rows.")
		if rej > 0:
			any_rejected = True

		if not d.po3_item and not d.soc3_item:
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
		# a short line has to say why before the receipt can move on
		if strict and vt == "Short" and not d.reject_reason:
			frappe.throw("Row " + str(d.idx) + " (" + (d.received_item_code or "") + "): counted "
				+ str(rec) + " of " + str(F(d.expected_qty)) + " expected - set a Reject Reason "
				+ "before this receipt can move on.")
		# "Other" is only a reason once it is written down
		if d.reject_reason == "Other" and not (d.remarks or "").strip():
			frappe.throw("Row " + str(d.idx) + " (" + (d.received_item_code or "") + "): Reject "
				+ "Reason is Other - write the reason in Remarks.")

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
				+ "<br><br>If the supplier genuinely sent extra, carry on. If the count "
				+ "is wrong, correct it now - after "
				+ "posting it becomes an over-receipt on the order.")


# ---------------------------------------------------------------------------
# Migrated from Server Script "GR3 Post To PO3"
# (DocType Event / After Submit on Purchase Receipt V3).
#
# Writes the counted quantities back onto the PO3 lines and re-derives each
# line status, reconciles the confirmation's backorders and any open shipments,
# rolls the order up to Partially Received / Received / Closed Short, and
# raises the native Purchase Receipt so stock actually moves.
#
# The PO is the source of truth for the order: a receipt records what arrived
# against it, but never changes its quantities, rates or totals, on the PO3 or
# the native PO.
# ---------------------------------------------------------------------------
def post_to_po3(doc):
	po = frappe.get_doc("Purchase Order V3", doc.purchase_order_v3)
	rows = {}
	for r in po.items:
		rows[r.name] = r

	open_bo_before = v3_open_bo(po.name)
	still_coming = {d.po3_item for d in doc.items if d.reject_reason == PARTIALLY_RECEIVED}
	for d in doc.items:
		if not d.po3_item:
			continue
		# only the ordered item fulfils the ordered line - a substitute, a wrong
		# variant or a wrong item never does; those are on the confirmation or a claim
		r = rows[d.po3_item]
		if d.received_item_code != r.item_code:
			continue
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
		elif d.po3_item in still_coming:
			# the rest is still coming - the next receipt expects it
			upd["line_status"] = "Partial"
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
		# a Substituted line is done with: its item is never coming, and what is
		# coming instead is followed on the confirmation (below)
		if r.line_status not in ("Received", "Closed Short", "Cancelled", "Supplier Stock Out", "Discontinued",
				"Substituted"):
			all_terminal = False
		elif r.name in open_bo_now:
			# goods are still owed on this line - nothing here is finished
			all_terminal = False
		if r.line_status in ("Closed Short", "Cancelled", "Supplier Stock Out", "Discontinued", "Substituted"):
			any_short = True
	# substitutes and new items still to come keep the order open
	if all_terminal and any(not ln.closed and ln.qty - ln.received > 0
			for ln in soc3_expected(frappe.get_doc("Purchase Order V3", po.name)).values()):
		all_terminal = False

	close_native_after = 0
	hdr = {}
	if all_terminal:
		hdr["receipt_status"] = "Closed Short" if any_short else "Received"
		hdr["workflow_state"] = "Closed Short" if any_short else "Closed"
		open_grs = frappe.get_all("Purchase Receipt V3",
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
			# the draft kept in step while counting, now with the final count
			pr = draft_native_pr(doc) or frappe.new_doc("Purchase Receipt")
			fill_native_pr(pr, doc, po, final=True)
			pr.save()
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
					+ "<br><br>Fix the cause, then use <b>Retry ERP Posting</b> on this Purchase Receipt 3.")

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
# The native Purchase Receipt twin, kept as a draft while counting.
#
# Like Purchase Order V3 and its native PO: the twin exists from the first save
# that has lines, follows every save of the count, and Post to Stock submits
# that same document rather than raising a new one. Until then it is a draft,
# so nothing has moved in stock.
#
# fill_native_pr is the one place a PR3 is turned into native lines -- posting,
# Retry ERP Posting and the draft sync all go through it. A draft keeps the
# lines not counted yet at zero (allow_zero_qty) so it reads like the count
# sheet; the final fill drops them, as ERPNext will not post a zero line.
# ---------------------------------------------------------------------------
def fill_native_pr(pr, doc, po, final):
	rows = {}
	for r in po.items:
		rows[r.name] = r
	npo = frappe.db.get_value("Purchase Order", po.erp_purchase_order,
		["currency", "conversion_rate", "buying_price_list"], as_dict=True)
	pr.supplier = doc.supplier
	pr.company = po.company
	pr.currency = npo.currency
	pr.conversion_rate = F(npo.conversion_rate) or 1
	pr.buying_price_list = npo.buying_price_list
	pr.purchase_order = po.erp_purchase_order
	pr.set("items", [])
	rate = {k: ln.rate for k, ln in soc3_expected(po, doc.name).items()}
	# what each native PO line can still take: the PO is never grown, so the
	# rest of an increased quantity goes on a row of its own
	room = {n.name: F(n.qty) - F(n.received_qty) for n in frappe.get_all("Purchase Order Item",
		filters={"parent": po.erp_purchase_order}, fields=["name", "qty", "received_qty"])}

	def add_row(d, accepted, rejected, po_item=None):
		row = pr.append("items", {})
		row.item_code = d.received_item_code
		row.qty = accepted
		row.rejected_qty = rejected
		row.warehouse = doc.warehouse
		row.rejected_warehouse = doc.rejected_warehouse
		# ours, not ERPNext's: it only looks at this exact supplier
		if d.supplier_part_no:
			row.supplier_part_no = d.supplier_part_no
		if po_item:
			row.purchase_order = po.erp_purchase_order
			row.purchase_order_item = po_item
		# the price the supplier confirmed, on the order's lines and off them
		if d.soc3_item and rate.get(d.soc3_item):
			row.rate = rate[d.soc3_item]
		elif po_item:
			row.rate = F(rows[d.po3_item].rate)
		row.neb_source_doctype = doc.doctype
		row.neb_source_name = doc.name
		row.neb_source_detail = d.name
		row.neb_box_no = doc.box_no

	for d in doc.items:
		if not d.received_item_code:
			continue
		acc, rej = F(d.accepted_qty), F(d.rejected_qty)
		if final and acc <= 0 and rej <= 0:
			continue
		r = rows.get(d.po3_item)
		# only the ordered item goes against the PO line; substitutes, new items
		# and wrong items are rows of their own
		po_item = r.erp_po_item if r and r.erp_po_item and d.received_item_code == r.item_code else None
		if not po_item:
			add_row(d, acc, rej)
			continue
		on_acc = min(acc, max(room.get(po_item, 0), 0))
		on_rej = min(rej, max(room.get(po_item, 0) - on_acc, 0))
		room[po_item] = room.get(po_item, 0) - on_acc - on_rej
		if on_acc > 0 or on_rej > 0 or not final:
			add_row(d, on_acc, on_rej, po_item)
		if acc - on_acc > 0 or rej - on_rej > 0:
			add_row(d, acc - on_acc, rej - on_rej)
	# the order's taxes and discount, as ERPNext's own PO -> Purchase Receipt
	# carries them (its mapper copies the tax rows and these settings): without
	# them the receipt, and an invoice made from it, came out without GST
	copy_taxes_to_native(pr, frappe.get_doc("Purchase Order", po.erp_purchase_order))
	pr.flags.allow_zero_qty = not final


def draft_native_pr(doc):
	if doc.erp_purchase_receipt and frappe.db.get_value("Purchase Receipt",
			doc.erp_purchase_receipt, "docstatus") == 0:
		return frappe.get_doc("Purchase Receipt", doc.erp_purchase_receipt)
	return None


def sync_native_pr(doc):
	# on_update also runs on the submit save; posting handles that one
	if doc.docstatus != 0:
		return
	pr = draft_native_pr(doc)

	# a rejected delivery is never posted, so its twin has nothing to become
	if doc.workflow_state == "Rejected":
		if pr:
			frappe.delete_doc("Purchase Receipt", pr.name, force=1, ignore_permissions=True)
			frappe.db.set_value(doc.doctype, doc.name, "erp_purchase_receipt", None,
				update_modified=False)
		return

	# already submitted or cancelled outside this flow - not ours to rewrite
	if not pr and doc.erp_purchase_receipt and frappe.db.exists("Purchase Receipt",
			doc.erp_purchase_receipt):
		return
	if not frappe.db.get_single_value("Procurement Settings V3", "posting_enabled"):
		return
	po = frappe.get_doc("Purchase Order V3", doc.purchase_order_v3)
	# a receipt can only be raised against a submitted native PO
	if not po.erp_purchase_order or frappe.db.get_value("Purchase Order",
			po.erp_purchase_order, "docstatus") != 1:
		return
	if not any(d.received_item_code for d in doc.items):
		return

	pr = pr or frappe.new_doc("Purchase Receipt")
	fill_native_pr(pr, doc, po, final=False)
	# A twin that will not save must not stop the count being saved - the
	# receiver is mid-scan. Say why, and Post to Stock tries again with the
	# final count.
	frappe.db.savepoint("prv3_native_pr")
	logged = len(frappe.local.message_log)
	try:
		pr.save()
	except Exception as e:
		frappe.db.rollback(save_point="prv3_native_pr")
		# drop the PR's own error popup; the count did save
		del frappe.local.message_log[logged:]
		msg = str(e)[:300]
		doc.post_error = "Draft Purchase Receipt not updated: " + msg
		frappe.db.set_value(doc.doctype, doc.name, "post_error", doc.post_error,
			update_modified=False)
		frappe.msgprint("This count was saved, but the draft Purchase Receipt "
			+ (doc.erp_purchase_receipt or "") + " was <b>not</b> updated to match:<br><br>" + msg
			+ "<br><br>Fix the cause and save again.",
			title="Purchase Receipt not updated", indicator="orange")
		return
	doc.erp_purchase_receipt = pr.name
	doc.post_error = None
	frappe.db.set_value(doc.doctype, doc.name, {"erp_purchase_receipt": pr.name,
		"post_error": None}, update_modified=False)


def delete_native_pr(doc):
	if draft_native_pr(doc):
		frappe.delete_doc("Purchase Receipt", doc.erp_purchase_receipt, force=1,
			ignore_permissions=True)


# ---------------------------------------------------------------------------
# Migrated from Server Script "GR3 Cancel Guard"
# (DocType Event / Before Cancel on Purchase Receipt V3).
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
# Builds the barcode/SKU -> item_code lookup the receipt form scans against,
# for the order's items and the confirmation's (substitutes, new items):
# item code, retail SKU suffix, every Item Barcode, and this supplier's part
# numbers, all upper-cased. Called once per receipt and cached client-side.
#
# No alias in hooks.py: the only caller is purchase_receipt_v3.js, repointed to
# this dotted path.
# ---------------------------------------------------------------------------
@frappe.whitelist()
def v3_gr3_scan_map(po3=None):
	supplier = frappe.db.get_value("Purchase Order V3", po3, "supplier")
	out = {}
	names = {}
	codes = frappe.get_all("Purchase Order V3 Item", filters={"parent": po3},
		pluck="item_code", limit_page_length=0)
	soc = live_confirmation(po3)
	if soc:
		for ln in frappe.get_all("Supplier Order Confirmation V3 Item", filters={"parent": soc},
				fields=["item_code", "substitute_item_code"]):
			codes += [ln.item_code, ln.substitute_item_code]
	for ic in codes:
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
# each -- from the supplier's confirmation (expected_rows) -- so the form can
# lay the grid out before anything is saved. Counts are
# always returned at zero -- the server re-derives them on save.
#
# No alias in hooks.py: the only caller is purchase_receipt_v3.js, repointed here.
# ---------------------------------------------------------------------------
@frappe.whitelist()
def v3_gr3_prefill_preview(po3=None, shipment=None):
	po = frappe.get_doc("Purchase Order V3", po3)

	# pick the shipment exactly as GR3 Validate And Classify does
	ship = shipment or pick_shipment(po)

	rows = []
	for x in expected_rows(po, ship):
		rows.append({"soc3_item": x.soc3_item, "po3_item": x.po3_item, "expected_item_code": x.item_code,
			"received_item_code": x.item_code, "expected_qty": x.expected_qty,
			"retail_sku_suffix": frappe.db.get_value("Item", x.item_code, "ifw_retailskusuffix")})

	frappe.response["message"] = {"shipment": ship, "warehouse": po.set_warehouse, "rows": rows}


# ---------------------------------------------------------------------------
# Migrated from Server Script "V3 Retry GR3 Posting"
# (API: v3_retry_gr3_posting).
#
# Recovery for a posted Purchase Receipt V3 whose native Purchase Receipt never
# made it: submits an existing draft PR, or builds and submits a new one.
# Backs the "Retry ERP Posting" button.
#
# No alias in hooks.py: the only caller is purchase_receipt_v3.js, repointed here.
# ---------------------------------------------------------------------------
@frappe.whitelist()
def v3_retry_gr3_posting(gr3=None):
	# v3_retry_gr3_posting?gr3=PR3-YYYY-NNNNN
	# Submits the draft PR a Purchase Receipt 3 already created, or creates one if the
	# earlier attempt never got that far. Safe to call repeatedly.
	name = gr3
	if not name:
		frappe.throw("pass gr3=<name>")
	doc = frappe.get_doc("Purchase Receipt V3", name)
	if doc.docstatus != 1 or doc.workflow_state != "Posted":
		frappe.throw(name + " is not Posted - nothing to retry.")

	if doc.erp_purchase_receipt and frappe.db.exists("Purchase Receipt", doc.erp_purchase_receipt):
		pr = frappe.get_doc("Purchase Receipt", doc.erp_purchase_receipt)
		if pr.docstatus == 1:
			frappe.db.set_value(doc.doctype, doc.name, {"post_error": None})
			frappe.response["message"] = {"status": "already submitted", "pr": pr.name}
		elif pr.docstatus == 2:
			frappe.throw("Purchase Receipt " + pr.name + " was cancelled. Amend it in ERP, or cancel this Purchase Receipt 3 and re-receive.")
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
		po_status = frappe.db.get_value("Purchase Order", po.erp_purchase_order, "status")
		if po_status == "Closed":
			try:
				frappe.get_doc("Purchase Order", po.erp_purchase_order).update_status("Submitted")
			except Exception:
				frappe.db.set_value("Purchase Order", po.erp_purchase_order, "status", "To Receive and Bill")
			frappe.msgprint("Native PO " + po.erp_purchase_order
				+ " was Closed - reopened so this receipt could post.")
		pr = frappe.new_doc("Purchase Receipt")
		fill_native_pr(pr, doc, po, final=True)
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
