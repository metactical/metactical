# Copyright (c) 2026, Storebuilder Commerce Inc and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from metactical.procurement_v3.utils import F


class ItemConversionV3(Document):
	def validate(self):
		validate(self)


# ---------------------------------------------------------------------------
# Migrated from Server Script "ICV3 Validate"
# (DocType Event / Before Save on Item Conversion V3).
#
# Checks the quantity, resolves the target item -- creating a "<source>-REF"
# refurb item from the source when asked to -- and refuses a conversion whose
# target is the same as its source.
# ---------------------------------------------------------------------------
def validate(doc):
	if F(doc.qty) <= 0:
		frappe.throw("Qty must be greater than zero.")

	if not doc.target_item:
		if not doc.create_target_item:
			frappe.throw("Set a Target Item, or tick 'Create Refurb Item If Missing'.")
		code = doc.source_item + "-REF"
		if frappe.db.exists("Item", code):
			doc.target_item = code
		else:
			src = frappe.get_doc("Item", doc.source_item)
			it = frappe.new_doc("Item")
			it.item_code = code
			it.item_name = ((src.item_name or src.name) + " (Refurb)")[:140]
			it.item_group = src.item_group
			it.stock_uom = src.stock_uom
			it.is_stock_item = 1
			it.brand = src.brand
			it.description = "Refurbished unit of " + src.name + ". Created by " + doc.doctype + "."
			it.insert()
			doc.target_item = it.name
			frappe.msgprint("Created refurb item " + it.name)

	if doc.target_item == doc.source_item:
		frappe.throw("Target item must be different from the source item.")
