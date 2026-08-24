# Copyright (c) 2026, Storebuilder Commerce Inc and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from metactical.procurement_v3.utils import F


class SupplierClaimV3(Document):
	def validate(self):
		validate(self)


# ---------------------------------------------------------------------------
# Migrated from Server Script "CLM3 Validate"
# (DocType Event / Before Save on Supplier Claim V3).
#
# Back-fills the order / supplier / receipt links, pulls the claimable lines off
# a Goods Receipt V3 (rejections, wrong items, unbilled overages), maps each
# one to a claim reason and claim type, and totals the claim value.
#
# claim_reason / claim_type_for / claimable stay nested, matching the original
# script's scoping.
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

	def claim_type_for(disposition):
		if disposition == "Return to Supplier":
			return "Refund"
		if disposition in ("Keep - Claim Credit", "Keep - Free of Charge", "Write Off", "Quarantine"):
			return "Credit"
		if disposition == "Accept as Substitution":
			return "None"
		return "Credit"

	def claimable(rejected, disposition, var_type, var_qty, overage_billed):
		if rejected > 0:
			return rejected
		if disposition in ("Return to Supplier", "Keep - Claim Credit",
				"Keep - Free of Charge", "Write Off"):
			return abs(var_qty) if var_qty else 0
		if var_type in ("Short", "Wrong Item", "Wrong Variant", "Unordered"):
			return abs(var_qty)
		if var_type == "Over" and overage_billed:
			return abs(var_qty)
		return 0

	total = 0.0
	if not doc.holding_warehouse:
		doc.holding_warehouse = frappe.db.get_single_value("Procurement Settings V3", "claims_warehouse")
	if doc.goods_receipt_v3 and not doc.purchase_order_v3:
		doc.purchase_order_v3 = frappe.db.get_value("Goods Receipt V3", doc.goods_receipt_v3, "purchase_order_v3")
	if doc.purchase_order_v3 and not doc.supplier:
		doc.supplier = frappe.db.get_value("Purchase Order V3", doc.purchase_order_v3, "supplier")
	if doc.goods_receipt_v3 and not doc.purchase_receipt:
		doc.purchase_receipt = frappe.db.get_value("Goods Receipt V3", doc.goods_receipt_v3, "erp_purchase_receipt")

	# --- prefill, only while the claim is empty and unsubmitted ---
	if doc.docstatus == 0 and not doc.items and (doc.goods_receipt_v3 or doc.purchase_order_v3):
		if doc.goods_receipt_v3:
			receipts = [{"name": doc.goods_receipt_v3}]
		else:
			receipts = frappe.get_all("Goods Receipt V3",
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
			for d in frappe.get_all("Goods Receipt V3 Item", filters={"parent": g.name},
					fields=["name", "po3_item", "expected_item_code", "received_item_code",
							"rejected_qty", "reject_reason", "variance_type", "variance_qty",
							"disposition", "overage_billed", "photo", "remarks"],
					order_by="idx", limit_page_length=0):
				qty = claimable(F(d.rejected_qty), d.disposition, d.variance_type,
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
				row.claim_type = claim_type_for(d.disposition)
				row.claim_amount = qty * rates.get(d.po3_item, 0)
				row.supplier_response = "Pending"
				row.goods_outcome = "Pending"
				row.goods_receipt_v3 = g.name
				row.gr3_item = d.name
				row.photo = d.photo
				row.remarks = d.remarks
				row.current_warehouse = doc.holding_warehouse

		if not doc.items:
			frappe.throw("Nothing on " + (doc.goods_receipt_v3 or doc.purchase_order_v3)
				+ " is claimable. A line becomes claimable when the receipt rejects "
				+ "some of it, or flags it Short / Wrong Item / Wrong Variant, or its "
				+ "disposition is Return to Supplier or Keep - Claim Credit. "
				+ "If it has already been claimed, look at the existing claim instead.")

		# when the claim came from one receipt only, carry its links across
		seen = []
		for d in doc.items:
			if d.goods_receipt_v3 and d.goods_receipt_v3 not in seen:
				seen.append(d.goods_receipt_v3)
		if len(seen) == 1:
			if not doc.goods_receipt_v3:
				doc.goods_receipt_v3 = seen[0]
			if not doc.purchase_receipt:
				doc.purchase_receipt = frappe.db.get_value("Goods Receipt V3", seen[0],
					"erp_purchase_receipt")

	for d in doc.items:
		if d.item_code and not d.item_name:
			d.item_name = frappe.db.get_value("Item", d.item_code, "item_name")
		total += F(d.claim_amount)
	doc.total_claim_amount = total
