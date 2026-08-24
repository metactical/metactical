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
