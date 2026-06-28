# Copyright (c) 2026, Storebuilder Commerce Inc and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document
from metactical.custom_scripts.payment_entry.payment_entry import make_refund

class USAePayRefund(Document):
	def on_submit(self):
		make_refund(self.name, self.payment_entry)