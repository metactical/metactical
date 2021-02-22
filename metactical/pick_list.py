from __future__ import unicode_literals
import frappe
import json
from six import iteritems
from frappe.model.document import Document
from frappe import _
from frappe.model.mapper import get_mapped_doc
from frappe.utils import cstr, flt, getdate, cint, nowdate, add_days, get_link_to_form, strip_html
from erpnext.stock.doctype.pick_list.pick_list import PickList
import barcode as _barcode
from io import BytesIO

def custom_before_save(self):
	rv = BytesIO()
	_barcode.get('code128', self.locations[0].sales_order).write(rv)
	bstring = rv.getvalue()
	self.barcode = bstring.decode('ISO-8859-1')
	
def custom_on_save(self, method):
	PickList.before_save = custom_before_save
	
@frappe.whitelist()
def before_save_on_create():
	PickList.before_save = custom_before_save
	
@frappe.whitelist()
def create_pick_list(source_name, target_doc=None):
	def update_item_quantity(source, target, source_parent):
		target.qty = flt(source.qty) - flt(source.delivered_qty)
		target.stock_qty = (flt(source.qty) - flt(source.delivered_qty)) * flt(source.conversion_factor)
		target.picked_qty = flt(source.qty) - flt(source.delivered_qty)

	doc = get_mapped_doc('Sales Order', source_name, {
		'Sales Order': {
			'doctype': 'Pick List',
			'validation': {
				'docstatus': ['=', 1]
			}
		},
		'Sales Order Item': {
			'doctype': 'Pick List Item',
			'field_map': {
				'parent': 'sales_order',
				'name': 'sales_order_item',
				'warehouse': 'warehouse'
			},
			'postprocess': update_item_quantity,
			'condition': lambda doc: abs(doc.delivered_qty) < abs(doc.qty) and doc.delivered_by_supplier!=1
		},
	}, target_doc)

	doc.purpose = 'Delivery'
	PickList.before_save = custom_before_save

	#doc.set_item_locations()

	return doc
	
@frappe.whitelist()
def save_cancel_reason(**args):
	args = frappe._dict(args)
	doc = frappe.get_doc("Pick List", args.docname)
	doc.db_set("cancel_reason", args.cancel_reason, notify=True)
	return 'Success'
