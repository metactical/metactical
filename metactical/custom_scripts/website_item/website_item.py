import frappe
from erpnext.e_commerce.doctype.website_item.website_item import WebsiteItem
import json

class CustomWebsiteItem(WebsiteItem):
	def before_insert(self):
		website_specs = frappe.db.get_all("MT Item Website Specification", filters={"parent": self.item_code}, fields=["label", "description", "mandatory", "sb_tag"])
		for spec in website_specs:
			website_spec = self.append("neb_website_specifications")
			website_spec.label = spec.label
			website_spec.description = spec.description
			website_spec.mandatory = spec.mandatory
			website_spec.sb_tag = spec.sb_tag

	def validate(self):
		super().validate()
		if self.neb_website_specifications:
			self.set("website_specifications", [])
			for row in self.neb_website_specifications:
				self.append("website_specifications", {
					"label": row.label,
					"description": row.description
				})


@frappe.whitelist()
def get_website_label_descriptions(*args, **kwargs):
	payload = frappe.form_dict
	if not payload:
		return []

	filters = json.loads(payload.filters)
	if not filters:
		return []

	if not filters["parent"]:
		return []

	parent = filters.get("parent")
	
	"""Used for providing auto-completions in child table."""
	if not frappe.has_permission("Item"):
		frappe.throw(_("No Permission"))
	
	return frappe.db.sql(f"""
		SELECT description FROM `tabWebsite Spec Label Descriptions`
		WHERE parent = {frappe.db.escape(parent)}
	""")
