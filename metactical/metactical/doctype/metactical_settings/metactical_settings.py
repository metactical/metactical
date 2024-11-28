# Copyright (c) 2024, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class MetacticalSettings(Document):
	def validate(self):
		has_default = 0
		for account in self.usaepay_accounts:
			if account.is_default:
				has_default += 1

		if has_default > 1:
			frappe.throw("Only one account can be default")
		
