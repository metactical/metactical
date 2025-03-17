# Copyright (c) 2024, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class PurolatorSettings(Document):
	def validate(self):
		# Check that no other settings is enabled
		if self.enabled:
			other_enabled = frappe.db.exists("Purolator Settings", {"enabled": 1, "name": ["!=", self.name]})
			if other_enabled:
				frappe.throw(f"Error: Only one Purolator Setting can be enabled at a time")
