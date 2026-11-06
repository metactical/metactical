import frappe
from frappe.model.document import Document


class FnBMenu(Document):
	def on_update(self):
		# the Item webhook condition is generated from the menus' item groups
		from metactical.custom_scripts.utils.fnb_sync import refresh_item_webhook_condition
		refresh_item_webhook_condition()
