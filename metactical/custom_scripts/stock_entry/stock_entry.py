from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from frappe import _
from frappe.model.mapper import get_mapped_doc, map_child_doc
from frappe.utils import flt
from erpnext.stock.doctype.stock_entry.stock_entry import StockEntry
from erpnext.stock.doctype.serial_no.serial_no import update_serial_nos_after_submit


def validate(self, method):
	user = frappe.session.user
	setting_exists = frappe.db.get_value("Stock Entry User Permissions", filters={"user": user})
	if setting_exists:
		s_warehouses = []
		t_warehouses = []
		settings = frappe.get_doc("Stock Entry User Permissions", setting_exists)
		for row in settings.source_warehouse:
			s_warehouses.append(row.warehouse)
			
		for row in settings.target_warehouse:
			t_warehouses.append(row.warehouse)
		
		for row in self.items:
			if row.s_warehouse not in s_warehouses:
				frappe.throw("Warehouse {} not in list of warehouse allowed for user {}".format(row.s_warehouse, frappe.session.user))
				
			if row.t_warehouse not in t_warehouses:
				frappe.throw("Warehouse {} not in list of warehouse allowed for user {}".format(row.t_warehouse, frappe.session.user))
				

def on_submit(self, method):
	frappe.db.set_value('Stock Entry', self.name, 'ais_submitted_date', frappe.utils.today())

@frappe.whitelist()
def create_stock_entry(source_name, target_doc=None):
	def update_item_quantity(source, target, source_parent):
		qty = flt(flt(source.stock_qty) - flt(source.ordered_qty))/ target.conversion_factor \
			if flt(source.stock_qty) > flt(source.ordered_qty) else 0
		target.qty = qty
		target.transfer_qty = qty * source.conversion_factor
		target.conversion_factor = source.conversion_factor
		
		target.t_warehouse = source.warehouse

	doc = get_mapped_doc('Sales Order', source_name, {
		'Sales Order': {
			'doctype': 'Stock Entry',
			'validation': {
				'docstatus': ['=', 1]
			},
			'field_map': {
				'sales_order_no': 'name'
			}
		},
		'Sales Order Item': {
			'doctype': 'Stock Entry Detail',
			'field_map': {
				'parent': 'sales_order',
				'name': 'sales_order_item',
				'warehouse': 't_warehouse'
			},
			'postprocess': update_item_quantity,
			'condition': lambda doc: doc.ordered_qty < doc.stock_qty
		},
	}, target_doc)

	doc.purpose = 'Transfer'

	return doc
	
@frappe.whitelist()
def get_permitted_source(doctype, txt, searchfield, start, page_len, filters):
	user = filters.get("user")
	warehouses = []
	if user:
		setting_exists = frappe.db.get_value("Stock Entry User Permissions", filters={"user": user})
		if setting_exists:
			warehouses = frappe.db.sql("""SELECT warehouse FROM `tabUser Permitted Warehouse` 
							WHERE warehouse LIKE %(txt)s AND parent= %(parent)s
							AND parentfield='source_warehouse'""", 
							{
								'txt': "%%%s%%" % txt,
								'parent': setting_exists
							})
			'''settings = frappe.get_doc("Stock Entry User Permissions", setting_exists)
			for row in settings.source_warehouse:
				warehouses.append([row.warehouse])'''
		else:
			#Retrun all warehouses
			warehouses = frappe.db.sql("""SELECT name FROM `tabWarehouse` WHERE is_group=0 AND disabled=0 AND name LIKE %(txt)s""", {'txt': "%%%s%%" % txt})
	return warehouses
	
@frappe.whitelist()
def get_permitted_target(doctype, txt, searchfield, start, page_len, filters):
	user = filters.get("user")
	warehouses = []
	if user:
		setting_exists = frappe.db.get_value("Stock Entry User Permissions", filters={"user": user})
		if setting_exists:
			warehouses = frappe.db.sql("""SELECT warehouse FROM `tabUser Permitted Warehouse` 
							WHERE warehouse LIKE %(txt)s AND parent= %(parent)s
							AND parentfield='target_warehouse'""", 
							{
								'txt': "%%%s%%" % txt,
								'parent': setting_exists
							})
			'''settings = frappe.get_doc("Stock Entry User Permissions", setting_exists)
			for row in settings.target_warehouse:
				warehouses.append([row.warehouse])'''
		else:
			#Retrun all warehouses
			warehouses = frappe.db.sql("""SELECT name FROM `tabWarehouse` WHERE is_group=0 AND disabled=0 AND name LIKE %(txt)s""", {'txt': "%%%s%%" % txt})
	return warehouses
	
@frappe.whitelist()
def get_default_transit(user):
	return frappe.db.get_value('Stock Entry User Permissions', user, 'add_to_transit')
					
