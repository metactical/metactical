# Copyright (c) 2024, Techlift Technologies and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document

class WebsiteSpecificationLabel(Document):
	def validate(self):
		for row in self.descriptions:
			row.description = row.description.strip()
