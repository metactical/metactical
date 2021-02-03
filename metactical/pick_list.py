from __future__ import unicode_literals
import frappe
import json
from six import iteritems
from frappe.model.document import Document
from frappe import _

def before_update(self):
	#Do nothing
	
@frappe.whitelist()
def create_pick_list(source_name, target_doc=None):
	def update_item_quantity(source, target, source_parent):
		target.qty = flt(source.qty) - flt(source.delivered_qty)
		target.stock_qty = (flt(source.qty) - flt(source.delivered_qty)) * flt(source.conversion_factor)

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

	doc.set_item_locations()

	return doc
