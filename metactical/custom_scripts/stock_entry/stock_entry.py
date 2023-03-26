from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from frappe import _
from frappe.model.mapper import get_mapped_doc, map_child_doc
from frappe.utils import flt
from erpnext.stock.doctype.stock_entry.stock_entry import StockEntry
from erpnext.stock.doctype.serial_no.serial_no import update_serial_nos_after_submit
import barcode as _barcode
from barcode.writer import ImageWriter
from io import BytesIO
from frappe.utils import cint, comma_or, cstr, flt, format_time, formatdate, getdate, nowdate
from erpnext.stock.stock_ledger import NegativeStockError, get_previous_sle, get_valuation_rate

class CustomStockEntry(StockEntry):
	def set_actual_qty(self):
		allow_negative_stock = cint(frappe.db.get_single_value("Stock Settings", "allow_negative_stock"))

		for d in self.get("items"):
			previous_sle = get_previous_sle(
				{
					"item_code": d.item_code,
					"warehouse": d.s_warehouse or d.t_warehouse,
					"posting_date": self.posting_date,
					"posting_time": self.posting_time,
				}
			)

			# get actual stock at source warehouse
			d.actual_qty = previous_sle.get("qty_after_transaction") or 0
			
			# get actual quantity at target wareous
			target_previous_sle = get_previous_sle(
				{
					"item_code": d.item_code,
					"warehouse": d.t_warehouse,
					"posting_date": self.posting_date,
					"posting_time": self.posting_time,
				}
			)
			d.ais_target_qoh = target_previous_sle.get("qty_after_transaction")

			# validate qty during submit
			if (
				d.docstatus == 1
				and d.s_warehouse
				and not allow_negative_stock
				and flt(d.actual_qty, d.precision("actual_qty"))
				< flt(d.transfer_qty, d.precision("actual_qty"))
			):
				frappe.throw(
					_(
						"Row {0}: Quantity not available for {4} in warehouse {1} at posting time of the entry ({2} {3})"
					).format(
						d.idx,
						frappe.bold(d.s_warehouse),
						formatdate(self.posting_date),
						format_time(self.posting_time),
						frappe.bold(d.item_code),
					)
					+ "<br><br>"
					+ _("Available quantity is {0}, you need {1}").format(
						frappe.bold(d.actual_qty), frappe.bold(d.transfer_qty)
					),
					NegativeStockError,
					title=_("Insufficient Stock"),
				)

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
	#STE Barcode
	sv = BytesIO()
	_barcode.get('code128', self.name).write(sv, {"module_width":0.4})
	stoBarcode = sv.getvalue()
	self.ais_ste_barcode = stoBarcode.decode('ISO-8859-1')

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
	
@frappe.whitelist()
def move_stock(source_name, target_doc=None):
	def set_missing_values(source, target):
		target.set_stock_entry_type()

	def update_item(source_doc, target_doc, source_parent):
		target_doc.t_warehouse = ""

		if source_doc.material_request_item and source_doc.material_request:
			add_to_transit = frappe.db.get_value("Stock Entry", source_name, "add_to_transit")
			if add_to_transit:
				warehouse = frappe.get_value(
					"Material Request Item", source_doc.material_request_item, "warehouse"
				)
				target_doc.t_warehouse = warehouse

		target_doc.s_warehouse = source_doc.t_warehouse
		target_doc.qty = source_doc.qty - source_doc.transferred_qty

	doclist = get_mapped_doc(
		"Stock Entry",
		source_name,
		{
			"Stock Entry": {
				"doctype": "Stock Entry",
				"field_map": {"name": "outgoing_stock_entry"},
				"validation": {"docstatus": ["=", 1]},
			},
			"Stock Entry Detail": {
				"doctype": "Stock Entry Detail",
				"field_map": {
					"name": "ste_detail",
					"parent": "against_stock_entry",
					"serial_no": "serial_no",
					"batch_no": "batch_no",
				},
				"postprocess": update_item,
				"condition": lambda doc: flt(doc.qty) - flt(doc.transferred_qty) > 0.01,
			},
		},
		target_doc,
		set_missing_values,
	)

	return doclist
