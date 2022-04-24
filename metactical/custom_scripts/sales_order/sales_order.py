from __future__ import unicode_literals
import frappe
import json
#from metactical.api.shipstation import create_orders
import barcode as _barcode
from barcode.writer import ImageWriter
from io import BytesIO


@frappe.whitelist()
def save_cancel_reason(**args):
	args = frappe._dict(args)
	doc = frappe.get_doc("Sales Order", args.docname)
	doc.db_set("cancel_reason", args.cancel_reason, notify=True)
	return 'Success'


@frappe.whitelist()
def get_open_count(**args):
	args = frappe._dict(args)

	doc = frappe.get_all("Stock Entry", 
		filters={
			'sales_order_no': args.docname,
			'purpose': 'Material Transfer',
		},
		fields=[
			'name', 'sales_order_no',
		])
	return doc
	
'''def on_update(self, method):
	if self.docstatus == 1:
		create_orders(self.name)'''
		
@frappe.whitelist()
def get_bin_details(item_code, warehouse):
	ret = {}
	ret = frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse},
			["projected_qty", "actual_qty", "reserved_qty"], as_dict=True, cache=True) \
				or {"projected_qty": 0, "actual_qty": 0, "reserved_qty": 0}
	is_stock = frappe.db.get_value("Item", {"name": item_code}, ["is_stock_item"])
	ret.update({"is_stock_item": is_stock})
	return ret
	
@frappe.whitelist()
def update_drop_shipping(items):
	data = json.loads(items)
	for item in data:
		if item.get("delivered_by_supplier") == 1:
			frappe.db.set_value("Sales Order Item", item.get("docname"), "delivered_by_supplier", item.get("delivered_by_supplier"))
			frappe.db.set_value("Sales Order Item", item.get("docname"), "supplier", item.get("supplier"))
			
@frappe.whitelist()
def change_warehouse(items):
	data = json.loads(items)
	for item in data:
		frappe.db.set_value("Sales Order Item", item.get("docname"), "warehouse", item.get("warehouse"))
		
@frappe.whitelist()
def save_close_reason(**args):
	args = frappe._dict(args)
	doc = frappe.get_doc("Sales Order", args.docname)
	doc.db_set("ais_close_reason", args.close_reason, notify=True)
	return 'Success'
