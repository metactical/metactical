# Copyright (c) 2026, Storebuilder Commerce Inc and contributors
# For license information, please see license.txt

import json

import frappe
from frappe.model.document import Document

from metactical.procurement_v3.utils import F, mirror_po3_status, v3_recalc_totals


class SupplierOrderConfirmationV3(Document):
	def validate(self):
		validate(self)

	def on_submit(self):
		mirror_to_po3(self)

	def on_update_after_submit(self):
		# confirmed_rate, remarks and the backorder rows stay editable after
		# submit, so the header totals have to follow them.
		set_totals(self)
		frappe.db.set_value(self.doctype, self.name, {
			"total_ordered_qty": self.total_ordered_qty,
			"total_qty": self.total_qty,
			"total_backorder_qty": self.total_backorder_qty,
			"total": self.total,
			"base_total": self.base_total}, update_modified=False)

	def before_cancel(self):
		cancel_guard(self)


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
# Line statuses where nothing ships now: Confirmed Qty is always 0. Mirrored as
# SOC3_ZERO_QTY_STATUSES in the form script.
ZERO_QTY_STATUSES = ("Back-ordered", "Supplier Stock Out", "Discontinued", "Cancelled by Supplier")


def validate(doc):
	def resolve_item(val):
		if frappe.db.exists("Item", val):
			return val
		hit = frappe.db.get_value("Item", {"ifw_retailskusuffix": val}, "name")
		if not hit:
			hit = frappe.db.get_value("Item Barcode", {"barcode": val}, "parent")
		return hit

	if doc.ai_parsed and not doc.source_document:
		frappe.throw("AI-parsed confirmations must have the source document attached.")

	po = frappe.get_doc("Purchase Order V3", doc.purchase_order_v3)
	if po.docstatus != 1:
		frappe.throw("Purchase Order V3 " + po.name + " is not submitted/approved yet.")

	# the confirmation is priced in whatever the order was placed in
	doc.currency = po.currency
	doc.conversion_rate = F(po.conversion_rate) or 1.0

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
		ii = item_identifiers(d.item_code, doc.supplier)
		d.item_name = ii["item_name"]
		d.retail_sku_suffix = ii["retail_sku_suffix"]
		d.barcode = ii["barcode"]
		d.supplier_part_no = ii["supplier_part_no"]
		# a row keyed or pasted in by item code arrives without a rate; the
		# supplier holding the order price is the same default a pulled line gets
		if not F(d.confirmed_rate):
			d.confirmed_rate = r.rate

		# nothing ships now on these, so there is no quantity to confirm -- set
		# it rather than make the user zero it by hand (the form does the same)
		if d.line_status in ZERO_QTY_STATUSES:
			d.confirmed_qty = 0
		# Confirmed with no quantity = the full outstanding qty. A different
		# non-zero quantity is left alone for the check below to catch: it is more
		# likely a partial with the wrong status than a typo worth overwriting.
		elif d.line_status == "Confirmed" and not F(d.confirmed_qty):
			d.confirmed_qty = d.ordered_qty

		q = F(d.confirmed_qty)
		o = F(d.ordered_qty)
		s = d.line_status
		if s == "Confirmed" and q != o:
			frappe.throw("Row " + str(d.idx) + " (" + (d.item_code or "")
				+ "): 'Confirmed' means the full outstanding qty (" + str(o) + "), got " + str(q)
				+ ". Use a 'Partial - ...' status for less.")
		if s in ("Partial - Balance Cancelled", "Partial - Balance Back-ordered") and not (0 < q < o):
			frappe.throw("Row " + str(d.idx) + " (" + (d.item_code or "") + "): '" + s
				+ "' requires 0 < Confirmed Qty < " + str(o))
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
		b.received_qty = F(rows[d.po3_item].received_qty)
		old = keep.get(d.po3_item)
		b.eta = (old.eta if old and old.eta else d.backorder_eta)
		b.status = (old.status if old else "Open")
		b.cancel_reason = (old.cancel_reason if old else None)
		b.remarks = (old.remarks if old else None)

	set_totals(doc)


# ---------------------------------------------------------------------------
# Header totals, printed under the Lines grid.
#
# Deliberately derived and never typed: the grid is what the supplier said, and
# a total that does not add up to the column above it is the thing people query.
# The same arithmetic runs in the form script so the numbers move while the
# confirmation is still being keyed in, before the first save.
# ---------------------------------------------------------------------------
def set_totals(doc):
	ordered = 0.0
	confirmed = 0.0
	amount = 0.0
	for d in (doc.items or []):
		ordered += F(d.ordered_qty)
		confirmed += F(d.confirmed_qty)
		amount += F(d.confirmed_qty) * F(d.confirmed_rate)

	backordered = 0.0
	for b in (doc.backorders or []):
		backordered += F(b.balance_qty)

	doc.total_ordered_qty = ordered
	doc.total_qty = confirmed
	doc.total_backorder_qty = backordered
	doc.total = amount
	doc.base_total = amount * (F(doc.conversion_rate) or 1.0)


# ---------------------------------------------------------------------------
# Migrated from Server Script "SOC3 Mirror To PO3"
# (DocType Event / After Submit on Supplier Order Confirmation V3).
#
# Pushes each confirmed line back onto its PO3 line (confirmed qty, line status,
# shortfall, backorder ETA), copies the confirmation number onto the header,
# and moves the order to Acknowledged once the supplier has replied.
# ---------------------------------------------------------------------------
def mirror_to_po3(doc):
	po = frappe.get_doc("Purchase Order V3", doc.purchase_order_v3)
	discontinued_items = []

	for d in doc.items:
		s = d.line_status
		prev = frappe.db.get_value("Purchase Order V3 Item", d.po3_item,
			["line_status", "confirmed_qty"], as_dict=True)
		total = F(d.confirmed_qty)
		if prev and prev.line_status == "Back-ordered":
			total = total + F(prev.confirmed_qty)
		upd = {"confirmed_qty": total}
		if s == "Confirmed":
			upd["line_status"] = "Confirmed"
		elif s == "Partial - Balance Cancelled":
			upd["line_status"] = "Partial"
			upd["short_qty"] = F(d.ordered_qty) - F(d.confirmed_qty)
		elif s == "Partial - Balance Back-ordered":
			upd["line_status"] = "Back-ordered"
			upd["backorder_status"] = "Open"
			upd["backorder_eta"] = d.backorder_eta
		elif s == "Back-ordered":
			# nothing ships now; the whole ordered qty is still due later, so the
			# PO3 line must not record a confirmed quantity of 0 as "nothing coming"
			upd["line_status"] = "Back-ordered"
			upd["backorder_status"] = "Open"
			upd["backorder_eta"] = d.backorder_eta
			upd["confirmed_qty"] = F(d.ordered_qty)
		elif s == "Supplier Stock Out":
			upd["line_status"] = "Supplier Stock Out"
			upd["short_qty"] = F(d.ordered_qty)
		elif s == "Discontinued":
			upd["line_status"] = "Discontinued"
			upd["short_qty"] = F(d.ordered_qty)
			# The supplier has discontinued the product, not just this order, so
			# carry it onto the Item itself. set_value rather than a full save: the
			# Item's own validation must never be able to block a confirmation.
			if d.item_code and not frappe.db.get_value("Item", d.item_code, "ifw_discontinued"):
				frappe.db.set_value("Item", d.item_code, "ifw_discontinued", 1)
				discontinued_items.append(d.item_code)
		elif s == "Cancelled by Supplier":
			upd["line_status"] = "Cancelled"
			upd["short_qty"] = F(d.ordered_qty)
		elif s == "Substituted":
			upd["line_status"] = "Substituted"
		frappe.db.set_value("Purchase Order V3 Item", d.po3_item, upd)

	if discontinued_items:
		frappe.msgprint("Marked <b>Discontinued</b> on the Item record: "
			+ ", ".join(discontinued_items))

	hdr = {}
	if not po.confirmation_no and doc.confirmation_no:
		hdr["confirmation_no"] = doc.confirmation_no
		hdr["confirmation_date"] = doc.confirmation_date
		hdr["confirmation_no_source"] = doc.confirmation_no_source or "Confirmation Number"

	covered = {}
	for soc in frappe.get_all("Supplier Order Confirmation V3",
			filters={"purchase_order_v3": po.name, "docstatus": 1}, fields=["name"]):
		for ln in frappe.get_all("Supplier Order Confirmation V3 Item",
				filters={"parent": soc.name}, fields=["po3_item"]):
			covered[ln.po3_item] = 1
	missing = 0
	for r in po.items:
		if r.name not in covered:
			missing += 1
	hdr["confirmation_status"] = "Confirmed" if missing == 0 else "Partially Confirmed"

	if po.workflow_state in ("Sent to Supplier", "Approved"):
		hdr["workflow_state"] = "Acknowledged"

	frappe.db.set_value("Purchase Order V3", po.name, hdr)

	# lines just went dead (stock out, discontinued, cancelled, partial) and the
	# order is long since submitted, so nothing else will re-add the header up
	v3_recalc_totals(po.name)

	mirror_po3_status(po.name)


# ---------------------------------------------------------------------------
# Migrated from Server Script "SOC3 Cancel Guard"
# (DocType Event / Before Cancel on Supplier Order Confirmation V3).
#
# The confirmation is the record of what the supplier promised, so it cannot be
# cancelled once shipments were built from it or stock has landed against the
# order. Points the user at "Supplier Cancelled" instead.
# ---------------------------------------------------------------------------
def cancel_guard(doc):
	blockers = []
	for s in frappe.get_all("Inbound Shipment V3",
			filters={"supplier_order_confirmation_v3": doc.name, "docstatus": ("<", 2)},
			fields=["name", "workflow_state"], limit_page_length=0):
		blockers.append("shipment " + s.name + " (" + str(s.workflow_state)
			+ ") was built from this confirmation")

	if doc.purchase_order_v3:
		got = 0.0
		for r in frappe.get_all("Purchase Order V3 Item",
				filters={"parent": doc.purchase_order_v3},
				fields=["received_qty"], limit_page_length=0):
			got = got + float(r.received_qty or 0)
		if got > 0:
			blockers.append("goods have already been received against "
				+ doc.purchase_order_v3 + " (" + str(got) + " units)")

	if blockers:
		frappe.throw("<b>" + doc.name + " cannot be cancelled.</b><br><br>"
			+ "<br>".join(blockers)
			+ "<br><br>The confirmation is the record of what the supplier promised; "
			+ "cancelling it would leave the shipments and receipts with nothing "
			+ "behind them. Use <b>Supplier Cancelled</b> on the order instead if "
			+ "the supplier has withdrawn.")


# ---------------------------------------------------------------------------
# The supplier's own identifiers for an item, for the form script.
#
# validate() fills these in on save; the form calls this so a line keyed or
# scanned in by hand carries its Supplier SKU straight away, instead of the
# column staying blank until the first save.
# ---------------------------------------------------------------------------
@frappe.whitelist()
def item_identifiers(item_code, supplier=None):
	return {
		"item_name": frappe.db.get_value("Item", item_code, "item_name"),
		"retail_sku_suffix": frappe.db.get_value("Item", item_code, "ifw_retailskusuffix"),
		# the item's first barcode, the same one PO3 puts on the order line
		"barcode": frappe.db.get_value("Item Barcode", {"parent": item_code}, "barcode", order_by="idx asc"),
		"supplier_part_no": frappe.db.get_value("Item Supplier",
			{"parent": item_code, "supplier": supplier}, "supplier_part_no") if supplier else None,
	}


# ---------------------------------------------------------------------------
# Everything a line shows, for lines the form holds but the server has not
# filled yet -- a freshly pulled, unsaved confirmation only carries what its
# PO3 lines had, and those were often missing barcode and supplier SKU.
# Used to complete the grid after a pull and every row of the download.
#
# lines: [{"item_code": ..., "po3_item": ...}], answered in the same order.
# po3_rate is the order price, the default when no confirmed rate was given.
# ---------------------------------------------------------------------------
@frappe.whitelist()
def line_details(lines, supplier=None):
	if isinstance(lines, str):
		lines = json.loads(lines)
	out = []
	for ln in lines or []:
		item_code = ln.get("item_code")
		d = item_identifiers(item_code, supplier) if item_code else {}
		d["po3_rate"] = F(frappe.db.get_value("Purchase Order V3 Item", ln.get("po3_item"), "rate")) \
			if ln.get("po3_item") else 0
		out.append(d)
	return out


# ---------------------------------------------------------------------------
# Migrated from Server Script "V3 SOC Bulk Status" (API: v3_soc_bulk_status).
#
#   GET  ?soc=SOC3-...  -> the confirmation's lines, for export
#   POST {"soc": ..., "rows": [...]} -> bulk-apply status/qty/ETA back onto a
#        draft confirmation
#
# The old endpoint name is aliased in hooks.py so external callers keep working.
# Body verbatim apart from the two form_dict/payload lookups becoming arguments.
# ---------------------------------------------------------------------------
@frappe.whitelist()
def v3_soc_bulk_status(soc=None, rows=None):
	# v3_soc_bulk_status
	#   GET  ?soc=SOC3-...            -> rows for export
	#   POST {"soc": "...", "rows": [{"item_code": "...", "confirmed_qty": 5,
	#         "line_status": "...", "backorder_eta": "YYYY-MM-DD", "remarks": "..."}]}
	def F(x):
		return float(x or 0)

	payload = {}
	if frappe.request and frappe.request.data:
		try:
			payload = json.loads(frappe.request.data) or {}
		except Exception:
			payload = {}

	name = payload.get("soc") or soc
	if not name:
		frappe.throw("pass soc=<name>")
	doc = frappe.get_doc("Supplier Order Confirmation V3", name)

	rows = payload.get("rows") or rows
	if not rows:
		out = []
		for d in doc.items:
			out.append({
				"item_code": d.item_code,
				"retail_sku": d.retail_sku_suffix,
				"supplier_sku": d.supplier_part_no,
				"barcode": d.barcode,
				"ordered_qty": F(d.ordered_qty),
				"confirmed_qty": F(d.confirmed_qty),
				"line_status": d.line_status,
				"backorder_eta": str(d.backorder_eta or ""),
				"confirmed_rate": F(d.confirmed_rate),
				"remarks": d.remarks or ""})
		frappe.response["message"] = {"soc": doc.name, "docstatus": doc.docstatus,
			"purchase_order_v3": doc.purchase_order_v3, "rows": out}
	else:
		if doc.docstatus != 0:
			frappe.throw(doc.name + " is not a draft - confirmed lines cannot be bulk-edited. Create a superseding confirmation instead.")
		by_item = {}
		for d in doc.items:
			by_item[d.item_code] = d
		applied = 0
		unknown = []
		for r in rows:
			code = str(r.get("item_code") or "").strip()
			d = by_item.get(code)
			if not d:
				hit = frappe.db.get_value("Item", {"ifw_retailskusuffix": code}, "name")
				if hit:
					d = by_item.get(hit)
			if not d:
				unknown.append(code)
				continue
			if r.get("line_status"):
				d.line_status = str(r.get("line_status")).strip()
			if r.get("confirmed_qty") is not None:
				d.confirmed_qty = F(r.get("confirmed_qty"))
			if r.get("backorder_eta"):
				d.backorder_eta = r.get("backorder_eta")
			if r.get("remarks") is not None:
				d.remarks = r.get("remarks")
			if r.get("confirmed_rate"):
				d.confirmed_rate = F(r.get("confirmed_rate"))
			applied += 1
		doc.save()
		frappe.response["message"] = {"soc": doc.name, "updated": applied, "unknown": unknown,
			"url": frappe.utils.get_url("/app/supplier-order-confirmation-v3/" + doc.name)}
