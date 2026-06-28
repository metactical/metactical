# Copyright (c) 2026, Storebuilder Commerce Inc and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document
from metactical.custom_scripts.utils.restock_notification import create_email_log

class RestockSubscriptionLog(Document):
	def on_submit(self):
		"""On submit, create a Restock Email Log for this subscription (if one doesn't already exist)."""
		create_email_log(self)