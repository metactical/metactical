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
from erpnext.selling.doctype.sales_order.sales_order import SalesOrder
from erpnext.accounts.party import get_party_account
from frappe import _, msgprint
from metactical.custom_scripts.utils.metactical_utils import queue_action
from metactical.custom_scripts.usaepay.usaepay_api import (
		get_transaction_from_usaepay, 
		get_token_hash, 
		create_refund, 
		get_card_token
	)

class SalesOrderCustom(SalesOrder):
	def validate(self):
		super(SalesOrderCustom, self).validate()
		self.pull_reserved_qty()
			
	def pull_reserved_qty(self):
		for row in self.items:
			#Check if bin exists
			exists = frappe.db.exists('Bin', {'item_code': row.item_code, 'warehouse': row.warehouse})
			if exists:
				reserved_qty = frappe.db.get_value('Bin', {'item_code': row.item_code, 
					'warehouse': row.warehouse}, 'reserved_qty')
				row.update({'sal_reserved_qty': reserved_qty})

	def submit(self):
		if len(self.items) > 25:
			msgprint(
				_(
					"The task has been enqueued as a background job. In case there is any issue on processing in background, the system will add a comment about the error on this document and revert to the Draft stage"
				)
			)
			queue_action(self, "submit", timeout=2000)
		else:
			self._submit()
			
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
			
		target.debit_to = get_party_account("Customer", source.customer, source.company)

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
	
	# Metactical Customization: Added ignore pricing rule to field mapping
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

@frappe.whitelist()
def refund_payment(docname, refund_amount):
	message = ""
	try:
		sales_order = frappe.get_doc("Sales Order", docname)
		usaepay_transaction_key = sales_order.get("neb_usaepay_transaction_key")
		
		metactical_settings = frappe.get_single("Metactical Settings")
		usaepay_url = metactical_settings.get("usaepay_url")
		token_hash = get_token_hash(metactical_settings)

		message += "<br>Token Hash Generated"

		headers = {
			"Content-Type": "application/json",
			"Authorization": token_hash
		}

		transaction = get_transaction_from_usaepay(usaepay_transaction_key, token_hash)

		if transaction:
			message += "<br>Transaction Found in USAePay"
			card_token = get_card_token(usaepay_url, transaction.get("key"), headers)
			message += "<br>Card Token Generated"

			transaction["creditcard"]["number"] = card_token

			payload, refund_response = create_refund(transaction, refund_amount, usaepay_url, headers)
			message += "<br>Refund Created in USAePay"
			
			create_log(payload, refund_response, message, "Sales Order", docname, refund_amount, "Refund")

			card_holder = "for " + refund_response.get("creditcard").get("cardholder") if refund_response.get("creditcard") else ""
			frappe.response["message"] = f"<b>{refund_response['auth_amount']}</b> is refunded successfully <b>{card_holder}</b>."
			frappe.response["success"] = True
		else:
			frappe.response["success"] = False
			frappe.response["message"] = "Transaction not found in USAePay"

	except Exception as e:
		frappe.log_error(title="Refund Payment Error", message=frappe.get_traceback())
		frappe.msgprint("Unable to refund payment: {0}".format(e), title="Error")

def create_log(payload, refund_response, message, doctype, docname, refund_amount, action):
	# Mask credit card token
	payload["creditcard"]["number"] = "****-****" + payload["creditcard"]["number"][-9:]

	frappe.get_doc({
		"doctype": "USAePay Log",
		"request": format_json_for_html(payload),
		"response": format_json_for_html(refund_response),
		"log": message,
		"date": frappe.utils.now(),
		"reference_docname": docname,
		"refund_amount": refund_amount,
		"action": action,
		"reference_doctype": doctype
	}).insert()

def format_json_for_html(data, indent_size=2):
    try:
        # Function to recursively format JSON
        def format_json(data, indent_level):
            lines = []
            for key, value in data.items():
                if isinstance(value, dict):
                    # Recursively format nested objects
                    lines.append(f'{" " * indent_level * indent_size}"{key}": {{ <br>')
                    lines.extend(format_json(value, indent_level + 1))
                    lines.append(f'{" " * indent_level * indent_size}}}, <br>')
                elif isinstance(value, list):
                    # Handle lists of objects
                    lines.append(f'{" " * indent_level * indent_size}"{key}": [ <br>')
                    for item in value:
                        lines.extend(format_json(item, indent_level + 1))
                    lines.append(f'{" " * indent_level * indent_size}] <br>')
                else:
                    # Format primitive types (string, number, etc.)
                    lines.append(f'{" " * indent_level * indent_size}"{key}": "{value}", <br>')
            return lines
        
        # Start formatting from the top-level object
        formatted_lines = format_json(data, indent_level=1)
        
        # Join all lines with newline characters
        formatted_json = '\n'.join(formatted_lines)
        
        return formatted_json
    
    except json.JSONDecodeError as e:
        return f"Error decoding JSON: {str(e)}"
    except Exception as e:
        return f"Error: {str(e)}"
