# Copyright (c) 2025, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from metactical.metactical.doctype.item_inventory_output.item_inventory_output import update_item_inventory_output

class FailedInventoryOutput(Document):
	pass

@frappe.whitelist()
def process_failed_inventory_outputs():
	failed_inventory_outputs = frappe.db.get_all("Failed Inventory Output", fields=["name", "item_code"])
	for failed_inventory_output in failed_inventory_outputs:
		try:
			frappe.enqueue(update_item_inventory_output, item_code=failed_inventory_output.item_code, queue='default')	
			frappe.db.delete("Failed Inventory Output", {"name": failed_inventory_output.name})
		except Exception as e:
			frappe.log_error(title="Failed to reprocess inventory output for item", message=frappe.get_traceback())