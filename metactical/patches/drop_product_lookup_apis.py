# Copyright (c) 2026, Storebuilder Commerce Inc and contributors
"""Storebuilder Sync Settings no longer has a Product Lookup APIs table. Remove its rows.

The lookup endpoint answered `GET ?external_id=` with one product, and Item Merge used it to find
the slug of a legacy product before a merge. `papi_product_details` does that and more - it answers
to a slug as well, and hands back the whole product - so step 1 asks it instead, through the
Product Detail APIs table beside it.

Removing the field leaves its `Item Import Validation` rows in the table with a parentfield nothing
reads: invisible in the form, still there in every `frappe.get_all("Item Import Validation")` that
does not filter on one. Those queries are how every Storebuilder API in this app is read, so the
rows are deleted rather than left to be picked up by the wrong one.
"""
import frappe

CHILD = "Item Import Validation"
PARENTFIELD = "product_lookup_apis"


def execute():
	if not frappe.db.table_exists(CHILD):
		return
	names = frappe.get_all(CHILD, filters={"parentfield": PARENTFIELD}, pluck="name")
	if not names:
		return
	frappe.db.delete(CHILD, {"name": ["in", names]})
	frappe.db.commit()
