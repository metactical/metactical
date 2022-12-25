# Copyright (c) 2022, Techlift Technologies and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document

class CanadaPost(Document):
	@property
	def host(self):
		return 'https://ct.soa-gw.canadapost.ca' if self.is_sandbox else 'https://soa-gw.canadapost.ca'
