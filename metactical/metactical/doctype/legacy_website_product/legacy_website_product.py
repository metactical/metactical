# Copyright (c) 2026, Storebuilder Commerce Inc and contributors
# For license information, please see license.txt
"""One legacy item's Storebuilder products: the websites it is live on and the slug on each.

Captured on the Item Merge page before the new variants are created, because the merge deletes the
legacy items and the slug is the only handle left on the product afterwards. Kept here rather than
on the Item for exactly that reason - the Item is going away.

One record per item, one row per website. An item on three websites is three rows here, not three
records, so opening it shows the whole picture at once.
"""
import frappe
from frappe.model.document import Document


class LegacyWebsiteProduct(Document):
	def validate(self):
		# "Not Published" is the operator saying this item has no Storebuilder product at all. It is
		# a decision, not a product, so it carries no websites.
		if self.status == "Not Published":
			self.websites = []
			return

		seen = set()
		for row in self.websites:
			row.slug = (row.slug or "").strip()
			if not (row.lead_source and row.slug):
				frappe.throw("Row {0}: a website and a slug are both needed".format(row.idx))
			if row.lead_source in seen:
				frappe.throw("{0} is on more than one row - one slug per website".format(row.lead_source))
			seen.add(row.lead_source)

			# The drop message and its confirmation both key on the price list, so a row without one
			# would be recorded and then never do anything.
			row.price_list = frappe.db.get_value("Lead Source", row.lead_source, "custom_neb_price_list")
			if not row.price_list:
				frappe.throw("{0} has no price list set, so a drop cannot be sent to it".format(row.lead_source))

			# One website, one slug, one item. Two items pointing at the same page would issue two
			# drops for the same product, and whichever is wrong takes a live product down with it.
			owner = frappe.db.get_value("Legacy Website Product Slug",
										{"parenttype": self.doctype, "parent": ["!=", self.name],
										 "lead_source": row.lead_source, "slug": row.slug},
										"parent")
			if owner:
				frappe.throw("{0} already has the slug {1} on {2}".format(owner, row.slug, row.lead_source))
