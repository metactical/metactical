import frappe
from erpnext.e_commerce.doctype.website_item.website_item import WebsiteItem

class CustomWebsiteItem(WebsiteItem):
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
    def copy_specification_from_item_group(self):
        self.set("neb_website_specifications", [])
        if self.item_group:
            for label, mandatory in frappe.db.get_values(
                "MT Item Website Specification", {"parent": self.item_group}, ["label", "mandatory"]
            ):
                row = self.append("neb_website_specifications")
                row.label = label
                row.mandatory = mandatory
