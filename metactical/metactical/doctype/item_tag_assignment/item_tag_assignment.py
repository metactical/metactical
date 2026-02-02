# Copyright (c) 2026, Storebuilder Commerce Inc and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ItemTagAssignment(Document):
	def validate(self):
		if not self.filters or self.filters == '[]':
			frappe.throw("Please set filters")
