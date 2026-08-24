# Copyright (c) 2026, Storebuilder Commerce Inc and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


def F(x):
	"""Numeric coercion helper, carried over verbatim from the V3 Server Scripts."""
	return float(x or 0)


class PurchaseOrderV3(Document):
	def before_insert(self):
		shared_series_naming(self)

	def validate(self):
		validate(self)


# ---------------------------------------------------------------------------
# Migrated from Server Script "PO3 Shared Series Naming"
# (DocType Event / Before Insert on Purchase Order V3).
#
# Creates the native Purchase Order twin first, then names this PO3 after it so
# the pair share one number. before_insert runs immediately before set_new_name,
# so setting flags.name_set here suppresses the PO3-.YYYY.-.##### autoname.
# ---------------------------------------------------------------------------
def shared_series_naming(doc):
	if not (doc.name and doc.name.startswith("PO3-")):
		npo = frappe.new_doc("Purchase Order")
		npo.supplier = doc.supplier
		npo.company = doc.company
		npo.transaction_date = doc.order_date or frappe.utils.nowdate()
		npo.schedule_date = doc.required_by
		npo.currency = doc.currency
		npo.conversion_rate = F(doc.conversion_rate) or 1
		npo.buying_price_list = doc.buying_price_list
		npo.set_warehouse = doc.set_warehouse
		for d in doc.items:
			r = npo.append("items", {})
			r.item_code = d.item_code
			r.qty = F(d.qty) or 1
			r.rate = F(d.rate)
			r.schedule_date = d.required_by or doc.required_by
			r.warehouse = d.warehouse or doc.set_warehouse
		npo.insert(ignore_permissions=True)
		doc.name = "PO3-" + npo.name
		doc.flags.name_set = True
		doc.erp_purchase_order = npo.name
		frappe.db.set_value("Purchase Order", npo.name, "custom_purchase_order_v3", doc.name)


# ---------------------------------------------------------------------------
# Migrated from Server Script "PO3 Validate"
# (DocType Event / Before Save on Purchase Order V3).
#
# Resolves currency / price list / FX, recomputes the line amounts and header
# totals, derives the approval tier, fills the supplier contact + ship-to
# defaults, and mirrors the workflow state onto the native PO twin.
# ---------------------------------------------------------------------------
def mirror_status_now(erp_po, state):
	# Before Save: the new state is only on the in-memory doc, not yet in the DB
	if erp_po:
		frappe.db.set_value("Purchase Order", erp_po,
			"custom_po3_status", state, update_modified=False)


def validate(doc):
	company_currency = frappe.db.get_value("Company", doc.company, "default_currency")

	# On new docs Frappe pre-fills Buying Settings' default price list and the
	# company currency BEFORE validate runs - do not mistake those for a user's
	# choice. The supplier's own defaults win; no supplier default = leave blank
	# so the mandatory check forces a manual pick.
	if doc.is_new() and doc.supplier:
		sup = frappe.db.get_value("Supplier", doc.supplier,
			["default_price_list", "default_currency"], as_dict=True) or {}
		global_pl = frappe.db.get_single_value("Buying Settings", "buying_price_list")
		if not doc.buying_price_list or doc.buying_price_list == global_pl:
			doc.buying_price_list = sup.default_price_list
		if sup.default_currency and (not doc.currency or doc.currency == company_currency):
			doc.currency = sup.default_currency
	if not doc.currency:
		doc.currency = company_currency
	if doc.currency and doc.currency != company_currency and F(doc.conversion_rate) in (0.0, 1.0):
		rate = frappe.db.get_value("Currency Exchange",
			{"from_currency": doc.currency, "to_currency": company_currency},
			"exchange_rate", order_by="date desc")
		if not rate:
			try:
				rate = frappe.call("erpnext.setup.utils.get_exchange_rate",
					from_currency=doc.currency, to_currency=company_currency)
			except Exception:
				rate = None
		if rate:
			doc.conversion_rate = rate
	if F(doc.conversion_rate) == 0:
		doc.conversion_rate = 1

	total_qty = 0.0
	total = 0.0
	for d in doc.items:
		if F(d.rate) == 0 and doc.buying_price_list and d.item_code:
			price = frappe.db.get_value("Item Price",
				{"item_code": d.item_code, "price_list": doc.buying_price_list, "buying": 1},
				"price_list_rate", order_by="valid_from desc")
			if price:
				d.rate = price
		d.amount = F(d.qty) * F(d.rate)
		total_qty += F(d.qty)
		total += d.amount
		if not d.warehouse:
			d.warehouse = doc.set_warehouse
		if not d.required_by:
			d.required_by = doc.required_by
		if d.item_code and d.variant_of and not d.variant_attributes:
			attrs = frappe.get_all("Item Variant Attribute", filters={"parent": d.item_code},
				fields=["attribute", "attribute_value"], order_by="idx")
			d.variant_attributes = ", ".join([(a.attribute + ": " + (a.attribute_value or "")) for a in attrs])

	doc.total_qty = total_qty
	doc.total = total
	doc.base_grand_total = total * (F(doc.conversion_rate) or 1.0)

	if doc.base_grand_total >= 50000:
		doc.approval_tier = "L3 (Abdul) - over 50k"
	elif doc.base_grand_total >= 10000:
		doc.approval_tier = "Manager - 10k to 50k"
	else:
		doc.approval_tier = "Buyer - under 10k"

	if doc.is_new():
		if not doc.supplier_email:
			doc.supplier_email = frappe.db.get_value("Supplier", doc.supplier, "po3_order_email")
		if not doc.cc_email:
			doc.cc_email = frappe.db.get_value("Supplier", doc.supplier, "po3_cc_email")
		if not doc.po_print_format:
			doc.po_print_format = frappe.db.get_value("Supplier", doc.supplier, "po3_print_format")

	doc.bcc_email = frappe.db.get_single_value("Procurement Settings V3", "bcc_email")

	if doc.set_warehouse:
		w = frappe.db.get_value("Warehouse", doc.set_warehouse,
			["warehouse_name", "address_line_1", "address_line_2", "city", "state", "pin"], as_dict=True)
		if w:
			parts = [w.warehouse_name, w.address_line_1, w.address_line_2, w.city, w.state, w.pin]
			doc.ship_to_display = ", ".join([p for p in parts if p])

	if not doc.ack_expected:
		doc.confirmation_status = "Not Requested"
	elif doc.confirmation_status == "Not Requested":
		doc.confirmation_status = "Awaiting"

	mirror_status_now(doc.erp_purchase_order, doc.workflow_state or "Draft")
