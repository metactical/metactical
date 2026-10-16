# Copyright (c) 2026, Storebuilder Commerce Inc and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from metactical.procurement_v3.utils import F


class SupplierClaimV3(Document):
	def validate(self):
		validate(self)

	def on_update(self):
		return_on_open(self)
		submit_returns_on_resolve(self)


# ---------------------------------------------------------------------------
# Migrated from Server Script "CLM3 Validate"
# (DocType Event / Before Save on Supplier Claim V3).
#
# Back-fills the order / supplier / receipt links, pulls the claimable lines off
# a Purchase Receipt V3 (rejections, wrong items, unbilled overages), maps each
# one to a claim reason and claim type, and totals the claim value.
#
# claim_reason / claimable stay nested, matching the original script's scoping.
# Every line starts as a Credit claim; the buyer changes the Claim Type per line.
# ---------------------------------------------------------------------------
def validate(doc):
	# A receipt line is claimable when the supplier owes us something for it:
	# goods rejected on arrival, or a variance the buyer has to chase.
	def claim_reason(rej_reason, var_type):
		if rej_reason == "Damaged":
			return "Damaged"
		if rej_reason == "Defective":
			return "Defective"
		if rej_reason in ("Expired", "Wrong Labelling", "Other"):
			return "Other"
		if var_type == "Short":
			return "Short Shipped But Billed"
		if var_type == "Wrong Item":
			return "Wrong Item"
		if var_type == "Wrong Variant":
			return "Wrong Variant"
		if var_type == "Damaged":
			return "Damaged"
		if var_type == "Over":
			return "Overage Billed"
		return "Other"

	def claimable(rejected, var_type, var_qty, overage_billed):
		if rejected > 0:
			return rejected
		if var_type in ("Short", "Wrong Item", "Wrong Variant", "Unordered"):
			return abs(var_qty)
		if var_type == "Over" and overage_billed:
			return abs(var_qty)
		return 0

	total = 0.0
	if not doc.holding_warehouse:
		doc.holding_warehouse = frappe.db.get_single_value("Procurement Settings V3", "claims_warehouse")
	if doc.purchase_receipt_v3 and not doc.purchase_order_v3:
		doc.purchase_order_v3 = frappe.db.get_value("Purchase Receipt V3", doc.purchase_receipt_v3, "purchase_order_v3")
	if doc.purchase_order_v3 and not doc.supplier:
		doc.supplier = frappe.db.get_value("Purchase Order V3", doc.purchase_order_v3, "supplier")
	if doc.purchase_receipt_v3 and not doc.purchase_receipt:
		doc.purchase_receipt = frappe.db.get_value("Purchase Receipt V3", doc.purchase_receipt_v3, "erp_purchase_receipt")

	# --- prefill, only while the claim is empty and unsubmitted ---
	if doc.docstatus == 0 and not doc.items and (doc.purchase_receipt_v3 or doc.purchase_order_v3):
		if doc.purchase_receipt_v3:
			receipts = [frappe._dict(name=doc.purchase_receipt_v3)]
		else:
			receipts = frappe.get_all("Purchase Receipt V3",
				filters={"purchase_order_v3": doc.purchase_order_v3, "docstatus": 1},
				fields=["name"], order_by="creation", limit_page_length=0)

		# anything already claimed elsewhere must not come through twice
		claimed = {}
		for c in frappe.get_all("Supplier Claim V3", filters={"docstatus": ("<", 2)},
				fields=["name"], limit_page_length=0):
			if c.name == doc.name:
				continue
			for ci in frappe.get_all("Supplier Claim V3 Item", filters={"parent": c.name},
					fields=["gr3_item", "qty"], limit_page_length=0):
				if ci.gr3_item:
					claimed[ci.gr3_item] = claimed.get(ci.gr3_item, 0) + F(ci.qty)

		rates = {}
		for r in frappe.get_all("Purchase Order V3 Item",
				filters={"parent": doc.purchase_order_v3},
				fields=["name", "rate"], limit_page_length=0):
			rates[r.name] = F(r.rate)

		for g in receipts:
			for d in frappe.get_all("Purchase Receipt V3 Item", filters={"parent": g.name},
					fields=["name", "po3_item", "expected_item_code", "received_item_code",
							"rejected_qty", "reject_reason", "variance_type", "variance_qty",
							"overage_billed", "photo", "remarks"],
					order_by="idx", limit_page_length=0):
				qty = claimable(F(d.rejected_qty), d.variance_type,
					F(d.variance_qty), d.overage_billed)
				qty = qty - claimed.get(d.name, 0)
				if qty <= 0:
					continue
				# a shortage is the ordered item never turning up; everything else
				# is about the goods that physically arrived
				if d.variance_type == "Short" and not F(d.rejected_qty):
					ic = d.expected_item_code or d.received_item_code
				else:
					ic = d.received_item_code or d.expected_item_code
				row = doc.append("items", {})
				row.item_code = ic
				row.item_name = frappe.db.get_value("Item", ic, "item_name") if ic else None
				row.qty = qty
				row.reason = claim_reason(d.reject_reason, d.variance_type)
				row.claim_type = "Credit"
				row.claim_amount = qty * rates.get(d.po3_item, 0)
				row.supplier_response = "Pending"
				row.goods_outcome = "Pending"
				row.purchase_receipt_v3 = g.name
				row.gr3_item = d.name
				row.photo = d.photo
				row.remarks = d.remarks
				row.current_warehouse = doc.holding_warehouse

		if not doc.items:
			frappe.throw("Nothing on " + (doc.purchase_receipt_v3 or doc.purchase_order_v3)
				+ " is claimable. A line becomes claimable when the receipt rejects "
				+ "some of it, or flags it Short / Wrong Item / Wrong Variant / Unordered, "
				+ "or an overage the supplier billed. "
				+ "If it has already been claimed, look at the existing claim instead.")

		# when the claim came from one receipt only, carry its links across
		seen = []
		for d in doc.items:
			if d.purchase_receipt_v3 and d.purchase_receipt_v3 not in seen:
				seen.append(d.purchase_receipt_v3)
		if len(seen) == 1:
			if not doc.purchase_receipt_v3:
				doc.purchase_receipt_v3 = seen[0]
			if not doc.purchase_receipt:
				doc.purchase_receipt = frappe.db.get_value("Purchase Receipt V3", seen[0],
					"erp_purchase_receipt")

	# Items is optional on the form so the prefill above can run; a claim
	# still needs something on it
	if not doc.items:
		frappe.throw("Add the claimed lines, or set a Purchase Receipt V3 / Purchase Order V3 "
			+ "to pull them in.")

	for d in doc.items:
		if d.item_code and not d.item_name:
			d.item_name = frappe.db.get_value("Item", d.item_code, "item_name")
		total += F(d.claim_amount)
	doc.total_claim_amount = total


# ---------------------------------------------------------------------------
# Sends claimed goods back: a native Purchase Receipt with Is Return checked,
# against the receipt the goods came in on.
#
# Built with ERPNext's own make_return_doc, so the return carries the original
# rates and links and is netted against anything already returned. Rejected
# stock goes back out of the rejected warehouse it was put in; anything else
# (wrong item, unbilled overage) out of the accepted warehouse. A claim line
# covering both takes the rejected stock first.
#
# Raised automatically when the claim is opened (return_on_open), and from
# Create > Purchase Return for anything added later. Left as a draft for the
# buyer to check and submit. A claim spanning several receipts gets one return
# per receipt.
# ---------------------------------------------------------------------------
NOT_RETURNABLE_OUTCOMES = ("Destroyed", "Refurbished", "Kept - Restocked", "Kept - Free of Charge")


def return_skip_reason(d):
	if d.purchase_return and frappe.db.get_value("Purchase Receipt", d.purchase_return, "docstatus") in (0, 1):
		return "already on return " + d.purchase_return
	if d.reason == "Short Shipped But Billed":
		return "short shipped - nothing arrived to send back"
	if d.goods_outcome in NOT_RETURNABLE_OUTCOMES:
		return "goods outcome is " + d.goods_outcome
	return None


# The native receipt a claim line's goods came in on. Lines pulled from a
# receipt carry their own Purchase Receipt V3; lines typed in by hand fall back
# to the claim's receipt.
def native_receipt_for(doc, d):
	pr3 = d.purchase_receipt_v3 or doc.purchase_receipt_v3
	if pr3:
		return frappe.db.get_value("Purchase Receipt V3", pr3, "erp_purchase_receipt")
	return doc.purchase_receipt


# Opening the claim is the decision to pursue it, so that is when the goods
# are sent back. Reopening a resolved claim runs it again; lines already on a
# return are skipped, so only what was added since goes out.
#
# Never blocks the transition: a claim with nothing to send back (shortages)
# just opens, and a return that will not save is reported and left for
# Create > Purchase Return.
def return_on_open(doc):
	if doc.workflow_state != "Open" or not doc.has_value_changed("workflow_state"):
		return
	frappe.db.savepoint("clm3_return")
	logged = len(frappe.local.message_log)
	try:
		made, skipped = create_purchase_returns(doc)
	except Exception as e:
		frappe.db.rollback(save_point="clm3_return")
		del frappe.local.message_log[logged:]
		frappe.msgprint("The Purchase Return could not be created:<br>" + str(e)[:300]
			+ "<br><br>Fix the cause, then use <b>Create &gt; Purchase Return</b>.",
			title="Purchase Return", indicator="orange")
		return
	if made:
		msg = "Draft Purchase Return created: " + ", ".join(
			'<a href="/app/purchase-receipt/' + n + '">' + n + "</a>" for n in made) + ". Review and submit it."
		if skipped:
			msg += "<br><br><b>Not returned:</b><br>" + "<br>".join(skipped)
		frappe.msgprint(msg, title="Purchase Return", indicator="green")


# Resolving the claim means the goods have gone back, so the returns are
# submitted -- that is what takes the stock out. Any returnable line still
# without a return gets one first. Unlike opening, this DOES block: a claim
# must not read Resolved while its goods are still on the shelf.
def submit_returns_on_resolve(doc):
	if doc.workflow_state != "Resolved" or not doc.has_value_changed("workflow_state"):
		return
	logged = len(frappe.local.message_log)
	try:
		create_purchase_returns(doc)
	except Exception as e:
		del frappe.local.message_log[logged:]
		frappe.throw("<b>" + doc.name + " cannot be resolved yet.</b><br><br>The Purchase Return "
			+ "could not be created:<br>" + str(e)[:300]
			+ "<br><br>Fix the cause, then mark the claim resolved again.",
			title="Purchase Return not created")

	submitted = []
	for n in sorted(set(d.purchase_return for d in doc.items if d.purchase_return)):
		ret = frappe.get_doc("Purchase Receipt", n)
		if ret.docstatus != 0:
			continue
		try:
			ret.submit()
		except Exception as e:
			del frappe.local.message_log[logged:]
			frappe.throw("<b>" + doc.name + " cannot be resolved yet.</b><br><br>Purchase Return "
				+ n + " could not be submitted:<br>" + str(e)[:300]
				+ "<br><br>Fix the cause, then mark the claim resolved again.",
				title="Purchase Return not submitted")
		submitted.append(n)

	# the goods went back with the return
	for d in doc.items:
		if d.purchase_return and d.goods_outcome in (None, "", "Pending") and frappe.db.get_value(
				"Purchase Receipt", d.purchase_return, "docstatus") == 1:
			d.goods_outcome = "Returned to Supplier"
			frappe.db.set_value(d.doctype, d.name, "goods_outcome", d.goods_outcome)

	if submitted:
		frappe.msgprint("Purchase Return submitted - stock sent back: " + ", ".join(
			'<a href="/app/purchase-receipt/' + n + '">' + n + "</a>" for n in submitted),
			title="Purchase Return", indicator="green")


@frappe.whitelist()
def make_purchase_return(claim):
	doc = frappe.get_doc("Supplier Claim V3", claim)
	doc.check_permission("write")
	made, skipped = create_purchase_returns(doc)
	if not made:
		frappe.throw("Nothing on " + doc.name + " can be returned.<br><br>" + "<br>".join(skipped))
	return {"returns": made, "skipped": skipped}


def create_purchase_returns(doc):
	from erpnext.controllers.sales_and_purchase_return import make_return_doc

	skipped = []
	by_pr = {}
	for d in doc.items:
		why = return_skip_reason(d)
		if not why:
			pr = native_receipt_for(doc, d)
			if not pr:
				why = "no receipt to return against - set the claim's Purchase Receipt V3"
			elif frappe.db.get_value("Purchase Receipt", pr, "docstatus") != 1:
				why = pr + " is not submitted"
		if why:
			skipped.append("Row " + str(d.idx) + " (" + (d.item_code or "") + "): " + why)
			continue
		by_pr.setdefault(pr, []).append(d)

	made = []
	for pr, lines in by_pr.items():
		ret = make_return_doc("Purchase Receipt", pr)
		pools = (
			# rejected stock first - it was already set aside for the supplier
			("rejected", {r.purchase_receipt_item: r for r in
				make_return_doc("Purchase Receipt", pr, return_against_rejected_qty=True).items}),
			("accepted", {r.purchase_receipt_item: r for r in ret.items}),
		)
		src = {}
		by_item = {}
		for r in frappe.get_all("Purchase Receipt Item", filters={"parent": pr},
				fields=["name", "item_code", "neb_source_detail"], order_by="idx", limit_page_length=0):
			src[r.neb_source_detail] = r.name
			by_item.setdefault(r.item_code, []).append(r.name)

		ret.set("items", [])
		used = {}
		returned = []
		for d in lines:
			# the exact receipt line when the claim line was pulled from it,
			# otherwise every receipt line of the same item
			if d.gr3_item and src.get(d.gr3_item):
				candidates = [src[d.gr3_item]]
			else:
				candidates = by_item.get(d.item_code, [])
			want = F(d.qty)
			for pool, rows in pools:
				for pri in candidates:
					r = rows.get(pri)
					if not r or want <= 0:
						continue
					take = min(want, -F(r.qty) - used.get((pool, pri), 0))
					if take <= 0:
						continue
					row = ret.append("items", r.as_dict(no_default_fields=True))
					cf = F(r.conversion_factor) or 1
					row.qty = row.received_qty = -take
					row.stock_qty = row.received_stock_qty = -take * cf
					row.rejected_qty = 0
					used[(pool, pri)] = used.get((pool, pri), 0) + take
					want -= take
			if want >= F(d.qty):
				skipped.append("Row " + str(d.idx) + " (" + (d.item_code or "")
					+ "): nothing left on " + pr + " to return")
				continue
			if want > 0:
				skipped.append("Row " + str(d.idx) + " (" + (d.item_code or "") + "): only "
					+ str(F(d.qty) - want) + " of " + str(F(d.qty)) + " left on " + pr + " to return")
			returned.append(d)
		if not ret.items:
			continue

		ret.remarks = "Return for Supplier Claim " + doc.name
		ret.insert()
		for d in returned:
			frappe.db.set_value(d.doctype, d.name, "purchase_return", ret.name)
			# the form gets this document back, so it has to show the link too
			d.purchase_return = ret.name
		made.append(ret.name)

	return made, skipped
