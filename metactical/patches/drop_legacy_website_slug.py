# Copyright (c) 2026, Storebuilder Commerce Inc and contributors
"""The Legacy Website Slug doctype is gone. Drop its table.

It existed only to back the Frappe child-table grid the Variants screen used for typing slugs in by
hand. Step 1 now reads them from `papi_product_details` instead and that grid was removed, so the
doctype has no controller, no parent and no reader left.

It was never a stored child table - the grid was mounted against the doctype and the rows lived in
the browser - so there is nothing in it to keep.
"""
import frappe

DOCTYPE = "Legacy Website Slug"


def execute():
	if not frappe.db.exists("DocType", DOCTYPE):
		return
	frappe.delete_doc("DocType", DOCTYPE, force=True, ignore_permissions=True)
	frappe.db.commit()
