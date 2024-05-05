# Copyright (c) 2022, Techlift Technologies and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document

class CycleCountV2(Document):
	def on_submit(self):
		doc = frappe.new_doc("Stock Reconciliation");
		doc.update({
			"purpose": "Stock Reconciliation",
			"ais_cycle_count_v2": self.name,
			"ais_reason_for_adjustment": self.reason_for_adjustment
		})
		for row in self.items:
			if row.qty != row.expected_qty:
				doc.append("items", {
					"item_code": row.item_code,
					"warehouse": self.warehouse,
					"qty": row.qty,
					"valuation_rate": row.valuation_rate
				})
		if hasattr(doc, "items"):
			doc.submit()
		
@frappe.whitelist()
def get_expected_qty(item_code, warehouse):
	expected = frappe.db.sql('''SELECT actual_qty, valuation_rate FROM `tabBin` 
								WHERE item_code = %(item_code)s AND warehouse = %(warehouse)s''', 
								{"item_code": item_code, "warehouse": warehouse}, as_dict=1)
	if expected and len(expected) > 0:
		ret = {"actual_qty": expected[0].actual_qty, "valuation_rate": expected[0].valuation_rate}
		return ret
	else:
		# Get valuation rate from Item
		valuation_rate = frappe.db.get_value("Item", item_code, "valuation_rate")
		return {"actual_qty": 0, "valuation_rate": valuation_rate}
		
@frappe.whitelist()
def get_permitted_warehouses(doctype, txt, searchfield, start, page_len, filters):
	user = filters.get("user")
	warehouses = []
	if user:
		setting_exists = frappe.db.get_value("Stock Entry User Permissions", filters={"user": user})
		if setting_exists:
			warehouses = frappe.db.sql("""SELECT warehouse FROM `tabUser Permitted Warehouse` 
							WHERE warehouse LIKE %(txt)s AND parent= %(parent)s
							AND parentfield='cycle_count_warehouse'""", 
							{
								'txt': "%%%s%%" % txt,
								'parent': setting_exists
							})
		else:
			#Retrun all warehouses
			warehouses = frappe.db.sql("""SELECT name FROM `tabWarehouse` WHERE is_group=0 AND disabled=0 AND name LIKE %(txt)s""", {'txt': "%%%s%%" % txt})
	return warehouses
	
@frappe.whitelist()
def get_items(warehouse, ifw_location):
	items = frappe.db.sql("""SELECT 
								item.item_code, bin.actual_qty, bin.valuation_rate
							FROM 
								`tabItem` AS item
							LEFT JOIN
								`tabBin` AS bin ON bin.item_code = item.item_code AND warehouse = '{0}'
							WHERE
								item.ifw_location LIKE '{1}'
							""".format(warehouse, '%' + ifw_location + '%'), as_dict=1)
	return items
