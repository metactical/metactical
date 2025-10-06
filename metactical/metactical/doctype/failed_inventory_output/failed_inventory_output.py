# Copyright (c) 2025, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from metactical.metactical.doctype.item_inventory_output.item_inventory_output import update_item_inventory_output

class FailedInventoryOutput(Document):
	pass

@frappe.whitelist()
def process_failed_inventory_outputs():
	# print("Testing sheduled task")
	# doc = frappe.get_doc("Failed Inventory Output", "4tuc5qj017")
	# doc.staus = "Processed"
	# doc.save()
	# frappe.db.commit()
	failed_inventory_outputs = frappe.db.get_all("Failed Inventory Output", fields=["name"])
	for failed_inventory_output in failed_inventory_outputs:
		doc = frappe.get_doc("Failed Inventory Output", failed_inventory_output.name)
		update_item_inventory_output(item_code=doc.item_code)
		frappe.enqueue(update_item_inventory_output, item_code=doc.item_code, queue='default')
