import frappe
from erpnext.e_commerce.doctype.website_item.website_item import WebsiteItem
import json

class CustomWebsiteItem(WebsiteItem):
	def before_insert(self):
		website_specs = frappe.db.get_all("MT Item Website Specification", filters={"parent": self.item_code}, fields=["label", "description", "mandatory", "sort_order"])
		for spec in website_specs:
			website_spec = self.append("neb_website_specifications")
			website_spec.label = spec.label
			website_spec.description = spec.description
			website_spec.mandatory = spec.mandatory
			website_spec.sort_order = spec.sort_order

	def validate(self):
		super().validate()
		if self.neb_website_specifications:
			self.set("website_specifications", [])
			for row in self.neb_website_specifications:
				self.append("website_specifications", {
					"label": row.label,
					"description": row.description
				})