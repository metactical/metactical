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
from erpnext.selling.doctype.sales_order.sales_order import SalesOrder, is_product_bundle, set_delivery_date
from erpnext.accounts.party import get_party_account
from frappe import _, msgprint
from metactical.custom_scripts.utils.metactical_utils import ( 
	queue_action
)

from metactical.custom_scripts.utils.metactical_utils import queue_action, check_si_payment_status_for_so
from metactical.metactical.doctype.item_inventory_output.item_inventory_output import update_item_inventory_output
from frappe.model.docstatus import DocStatus
from frappe.integrations.doctype.webhook.webhook import enqueue_webhook

class SalesOrderCustom(SalesOrder):
	def save(self):
		if self.docstatus == DocStatus.submitted() and len(self.items) > 25 and \
			self.ais_queue_status and self.ais_queue_status != "Queued":
			msgprint(
				_(
					"The task has been enqueued as a background job. In case there is \
					any issue on processing in background, the system will add a comment \
					about the error on this document and revert to the Draft stage"
				)
			)
			queue_action(self, "submit", timeout=2000)
		else:
			super().save()

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

	def set_status(self, update=False, status=None, update_modified=True):
		super(SalesOrderCustom, self).set_status(update, status, update_modified)
		from_ui = frappe.flags.get('from_ui', False)

		# Metactical Customization: Added
		if self.billing_status == "Fully Billed" and not self.neb_payment_completed_at:
			all_invoices_paid = check_si_payment_status_for_so(self.name)
			if all_invoices_paid:
				self.db_set("neb_payment_completed_at", frappe.utils.getdate(frappe.utils.now()), notify=True)

		if self.status in ["To Deliver", "To Bill", "To Deliver and Bill"] and not from_ui:
			# check if there is return delivery note created in 
			has_linked_return = False
			return_delivery_notes = get_return_delivery_note(self.name)
			if not return_delivery_notes:
				return_sales_invoices = get_return_sales_invoices(self.name)
				if return_sales_invoices:
					has_linked_return = True
			else:
				has_linked_return = True
    
			if has_linked_return:
				self.db_set("status", "Closed", notify=True)	
   
	def on_submit(self):
		super(SalesOrderCustom, self).on_submit()

		# Metactical Customization: Added
		for item in self.items:
			frappe.enqueue(update_item_inventory_output, item_code=item.item_code, voucher_type="Sales Order", queue='default')

	def on_cancel(self):
		super(SalesOrderCustom, self).on_cancel()

		# Metactical Customization: Added
		for item in self.items:
			frappe.enqueue(update_item_inventory_output, item_code=item.item_code, voucher_type="Sales Order", queue='default')

	def on_update_after_submit(self):
		super().on_update_after_submit()

		doc_before_update = self.get_doc_before_save()
		# Metactical Customization: Check if shipping or billing address has changed
		# and enqueue webhook if it has changed
		if doc_before_update and doc_before_update.docstatus == 1:
			original_shipping_address = doc_before_update.shipping_address
			original_billing_address = doc_before_update.address_display
   
			if self.shipping_address != original_shipping_address or self.address_display != original_billing_address:
				webhook = frappe.db.exists("Webhook", {
					"webhook_doctype": "Sales Order",
					"webhook_docevent": "on_update_after_submit",
					"enabled": 1
				})
    
				if webhook:
					doc = frappe.get_doc("Sales Order", self.name)
					enqueue_webhook(doc, frappe.get_doc("Webhook", webhook))

		for item in self.items:
			frappe.enqueue(update_item_inventory_output, item_code=item.item_code, queue='default')

	def update_delivery_status(self):
		"""Update delivery status from Purchase Order for drop shipping"""
		tot_qty, delivered_qty = 0.0, 0.0

		for item in self.items:
			if item.delivered_by_supplier:
				# Metactical Customization: If this SO item is a product bundle, 
				# compute delivered qty from its components
				if self.has_product_bundle(item.item_code):
					components = frappe.get_all(
						"Product Bundle Item",
						filters={"parent": item.item_code},
						fields=["item_code", "qty"],
					)

					bundles_possible = []
					for comp in components:
						# Sum delivered PO qty for this component, tied to this SO
						res = frappe.db.sql(
							"""
							SELECT COALESCE(SUM(poi.qty), 0)
							FROM `tabPurchase Order Item` poi
							INNER JOIN `tabPurchase Order` po ON po.name = poi.parent
							WHERE po.docstatus = 1
							  AND po.status = 'Delivered'
							  AND poi.sales_order = %s
							  AND poi.item_code = %s
							  AND (
									IFNULL(poi.product_bundle, '') = %s
								 OR IFNULL(poi.sales_order_item, '') = %s
							  )
							""",
							(self.name, comp.item_code, item.item_code, item.name),
						)
						delivered_comp_qty = flt(res[0][0]) if res else 0.0
						per_bundle_qty = flt(comp.qty or 0)
						# Avoid division by zero; if comp qty is 0, treat as not limiting
						if per_bundle_qty > 0:
							bundles_possible.append(delivered_comp_qty / per_bundle_qty)

					# Full bundles delivered is the min across components (floored)
					full_bundles_delivered = int(min(bundles_possible)) if bundles_possible else 0
					item.db_set(
						"delivered_qty",
						min(flt(item.qty), flt(full_bundles_delivered)),
						update_modified=False,
					)
				else:
					# Non-bundle: existing drop-ship delivered qty from PO status
					item_delivered_qty = frappe.db.sql(
						"""select sum(qty)
						from `tabPurchase Order Item` poi, `tabPurchase Order` po
						where poi.sales_order_item = %s
							and poi.item_code = %s
							and poi.parent = po.name
							and po.docstatus = 1
							and po.status = 'Delivered'""",
						(item.name, item.item_code),
					)
					item_delivered_qty = item_delivered_qty[0][0] if item_delivered_qty else 0
					item.db_set("delivered_qty", flt(item_delivered_qty), update_modified=False)

			delivered_qty += item.delivered_qty
			tot_qty += item.qty

		if tot_qty != 0:
			self.db_set("per_delivered", flt(delivered_qty / tot_qty) * 100, update_modified=False)
   
   
def get_return_delivery_note(sales_order):
	rows = frappe.db.sql("""
				SELECT DISTINCT
					dn.name AS delivery_note, dn.status
				FROM `tabDelivery Note` dn
				JOIN `tabDelivery Note Item` dni
				ON dni.parent = dn.name
				WHERE  dni.against_sales_order = %(sales_order)s
				AND dn.docstatus = 1
				AND dn.status != 'Cancelled'
				AND dn.is_return = 1
			""", {"sales_order": sales_order}, as_dict=True)	
   
	return rows

def get_return_sales_invoices(sales_order):
	rows = frappe.db.sql("""
				SELECT DISTINCT
					si.name AS sales_invoice, si.status
				FROM `tabSales Invoice` si
				JOIN `tabSales Invoice Item` sii
				ON sii.parent = si.name
				WHERE  sii.sales_order = %(sales_order)s
				AND si.docstatus = 1
				AND si.status != 'Cancelled'
				AND si.is_return = 1
				AND si.update_stock = 1
			""", {"sales_order": sales_order}, as_dict=True)	
   
	return rows


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

	return doclist

@frappe.whitelist()
def submit_order(doc):
	# Metactical Customization: Submit order in background if more than 10 items
	doc = frappe.get_doc("Sales Order", doc)
	if len(doc.items) > 25:
		msgprint(
			_(
				"The task has been enqueued as a background job. In case there is any issue on processing in background, the system will add a comment about the error on this document and revert to the Draft stage"
			)
		)
		queue_action(doc, "submit", timeout=2000)
	else:
		doc._submit()
  
@frappe.whitelist()
def update_status(status, name):
	so = frappe.get_doc("Sales Order", name)
	frappe.flags.from_ui = True
	so.update_status(status)

@frappe.whitelist()
def make_purchase_order(source_name, selected_items=None, target_doc=None):
	if not selected_items:
		return

	if isinstance(selected_items, str):
		selected_items = json.loads(selected_items)

	items_to_map = [
		item.get("item_code") for item in selected_items if item.get("item_code") and item.get("item_code")
	]
	items_to_map = list(set(items_to_map))

	def is_drop_ship_order(target):
		drop_ship = True
		for item in target.items:
			if not item.delivered_by_supplier:
				drop_ship = False
				break

		return drop_ship

	def set_missing_values(source, target):
		target.supplier = ""
		target.apply_discount_on = ""
		target.additional_discount_percentage = 0.0
		target.discount_amount = 0.0
		target.inter_company_order_reference = ""
		target.shipping_rule = ""
		target.tc_name = ""
		target.terms = ""
		target.payment_terms_template = ""
		target.payment_schedule = []

		if is_drop_ship_order(target):
			target.customer = source.customer
			target.customer_name = source.customer_name
			target.shipping_address = source.shipping_address_name
		else:
			target.customer = target.customer_name = target.shipping_address = None

		target.run_method("set_missing_values")
		target.run_method("calculate_taxes_and_totals")

	def update_item(source, target, source_parent):
		target.schedule_date = source.delivery_date
		target.qty = flt(source.qty) - (flt(source.ordered_qty) / flt(source.conversion_factor))
		target.stock_qty = flt(source.stock_qty) - flt(source.ordered_qty)
		target.project = source_parent.project

	def update_item_for_packed_item(source, target, source_parent):
		target.qty = flt(source.qty) - flt(source.ordered_qty)
		for item in source_parent.items:
			if item.item_code == source.parent_item:
				target.delivered_by_supplier = item.delivered_by_supplier
				break

	# po = frappe.get_list("Purchase Order", filters={"sales_order":source_name, "supplier":supplier, "docstatus": ("<", "2")})
	doc = get_mapped_doc(
		"Sales Order",
		source_name,
		{
			"Sales Order": {
				"doctype": "Purchase Order",
				"field_no_map": [
					"address_display",
					"contact_display",
					"contact_mobile",
					"contact_email",
					"contact_person",
					"taxes_and_charges",
					"shipping_address",
				],
				"validation": {"docstatus": ["=", 1]},
			},
			"Sales Order Item": {
				"doctype": "Purchase Order Item",
				"field_map": [
					["name", "sales_order_item"],
					["parent", "sales_order"],
					["stock_uom", "stock_uom"],
					["uom", "uom"],
					["conversion_factor", "conversion_factor"],
					["delivery_date", "schedule_date"],
				],
				"field_no_map": [
					"rate",
					"price_list_rate",
					"item_tax_template",
					"discount_percentage",
					"discount_amount",
					"supplier",
					"pricing_rules",
				],
				"postprocess": update_item,
				"condition": lambda doc: doc.ordered_qty < doc.stock_qty
				and doc.item_code in items_to_map
				and not is_product_bundle(doc.item_code),
			},
			"Packed Item": {
				"doctype": "Purchase Order Item",
				"field_map": [
					["name", "sales_order_packed_item"],
					["parent", "sales_order"],
					["uom", "uom"],
					["conversion_factor", "conversion_factor"],
					["parent_item", "product_bundle"],
					["rate", "rate"],
				],
				"field_no_map": [
					"price_list_rate",
					"item_tax_template",
					"discount_percentage",
					"discount_amount",
					"supplier",
					"pricing_rules",
				],
				"postprocess": update_item_for_packed_item,
				"condition": lambda doc: doc.parent_item in items_to_map,
			},
		},
		target_doc,
		set_missing_values,
	)

	set_delivery_date(doc.items, source_name)

	return doc