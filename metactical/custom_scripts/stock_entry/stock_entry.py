from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from frappe import _
from frappe.model.mapper import get_mapped_doc, map_child_doc
from frappe.utils import flt
from erpnext.stock.doctype.stock_entry.stock_entry import StockEntry


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
