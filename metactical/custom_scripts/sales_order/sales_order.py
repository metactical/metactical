from __future__ import unicode_literals
import frappe
import json
#from metactical.api.shipstation import create_orders
import barcode as _barcode
from barcode.writer import ImageWriter
from io import BytesIO
from frappe.model.mapper import get_mapped_doc
from frappe.utils import add_days, cint, cstr, flt, get_link_to_form, getdate, nowdate, strip_html
from erpnext.stock.doctype.item.item import get_item_defaults
from erpnext.setup.doctype.item_group.item_group import get_item_group_defaults
from frappe.model.utils import get_fetch_values

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
	
@frappe.whitelist()
def make_sales_invoice(source_name, target_doc=None, ignore_permissions=False):
	def postprocess(source, target):
		set_missing_values(source, target)
		# Get the advance paid Journal Entries in Sales Invoice Advance
		if target.get("allocate_advances_automatically"):
			target.set_advances()

	def set_missing_values(source, target):
		target.flags.ignore_permissions = True
		target.run_method("set_missing_values")
		target.run_method("set_po_nos")
		target.run_method("calculate_taxes_and_totals")

		if source.company_address:
			target.update({"company_address": source.company_address})
		else:
			# set company address
			target.update(get_company_address(target.company))

		if target.company_address:
			target.update(get_fetch_values("Sales Invoice", "company_address", target.company_address))

		# set the redeem loyalty points if provided via shopping cart
		if source.loyalty_points and source.order_type == "Shopping Cart":
			target.redeem_loyalty_points = 1

	def update_item(source, target, source_parent):
		target.amount = flt(source.amount) - flt(source.billed_amt)
		target.base_amount = target.amount * flt(source_parent.conversion_rate)
		target.qty = (
			target.amount / flt(source.rate)
			if (source.rate and source.billed_amt)
			else source.qty - source.returned_qty
		)

		if source_parent.project:
			target.cost_center = frappe.db.get_value("Project", source_parent.project, "cost_center")
		if target.item_code:
			item = get_item_defaults(target.item_code, source_parent.company)
			item_group = get_item_group_defaults(target.item_code, source_parent.company)
			cost_center = item.get("selling_cost_center") or item_group.get("selling_cost_center")

			if cost_center:
				target.cost_center = cost_center

	doclist = get_mapped_doc(
		"Sales Order",
		source_name,
		{
			"Sales Order": {
				"doctype": "Sales Invoice",
				"field_map": {
					"party_account_currency": "party_account_currency",
					"payment_terms_template": "payment_terms_template",
					"ignore_pricing_rule": "ignore_pricing_rule"
				},
				"field_no_map": ["payment_terms_template"],
				"validation": {"docstatus": ["=", 1]},
			},
			"Sales Order Item": {
				"doctype": "Sales Invoice Item",
				"field_map": {
					"name": "so_detail",
					"parent": "sales_order",
				},
				"postprocess": update_item,
				"condition": lambda doc: doc.qty
				and (doc.base_amount == 0 or abs(doc.billed_amt) < abs(doc.amount)),
			},
			"Sales Taxes and Charges": {"doctype": "Sales Taxes and Charges", "add_if_empty": True},
			"Sales Team": {"doctype": "Sales Team", "add_if_empty": True},
		},
		target_doc,
		postprocess,
		ignore_permissions=ignore_permissions,
	)

	automatically_fetch_payment_terms = cint(
		frappe.db.get_single_value("Accounts Settings", "automatically_fetch_payment_terms")
	)
	if automatically_fetch_payment_terms:
		doclist.set_payment_schedule()

	doclist.set_onload("ignore_price_list", True)

	return doclist
