import frappe
from erpnext.e_commerce.doctype.website_item.website_item import WebsiteItem
import json

# class CustomWebsiteItem(WebsiteItem):
# 	def validate(self):
# 		super().validate()
# 		if self.neb_website_specifications:
# 			self.set("website_specifications", [])
# 			for row in self.neb_website_specifications:
# 				self.append("website_specifications", {
# 					"label": row.label,
# 					"description": row.description
# 				})


# 	# @frappe.whitelist()
# 	# def copy_specification_from_item_group(self):
# 	# 	self.set("neb_website_specifications", [])
# 	# 	if self.item_group:
# 	# 		for label, mandatory in frappe.db.get_values(
# 	# 			"MT Item Website Specification", {"parent": self.item_group}, ["label", "mandatory"]
# 	# 		):
# 	# 			row = self.append("neb_website_specifications")
# 	# 			row.label = label
# 	# 			row.mandatory = mandatory

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
