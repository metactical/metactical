# Copyright (c) 2026, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

# Must match TRANSFER_RULES_CACHE_KEY in
# metactical.doctype.item_inventory_output.item_inventory_output
TRANSFER_RULES_CACHE_KEY = "warehouse_transfer_calculation_rules"

class WarehouseTransferCalculationRule(Document):
	def on_update(self):
		frappe.cache().delete_value(TRANSFER_RULES_CACHE_KEY)
