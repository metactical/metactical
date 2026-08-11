import frappe
from erpnext.controllers.buying_controller import BuyingController
from six import string_types
from frappe.model.mapper import get_mapped_doc
from frappe.model.utils import get_fetch_values
from frappe import msgprint, _
from frappe.utils import cint, cstr, flt, getdate, new_line_sep, nowdate, add_days
from erpnext.accounts.party import (
	get_address_tax_category,
	get_party_details as erpnext_get_party_details,
)
from erpnext.buying.doctype.purchase_order.purchase_order import PurchaseOrder
from frappe.utils import flt, cstr, now, get_datetime_str, file_lock, date_diff, now_datetime
from frappe import _, msgprint, is_whitelisted
from frappe.model.docstatus import DocStatus
from metactical.custom_scripts.utils.metactical_utils import queue_action

try:
	from frappe.contacts.doctype.address.address import render_address
except ImportError:
	from frappe.contacts.doctype.address.address import get_address_display as render_address

class CustomPurchaseOrder(PurchaseOrder):
	def save(self):
		if self.docstatus == DocStatus.submitted() and len(self.items) > 100 and \
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

	def onload(self):
		super(CustomPurchaseOrder, self).onload()
		if self.docstatus == 1:
			#Check if has Purchase Receipt
			has_pr = frappe.db.sql("""SELECT name FROM `tabPurchase Receipt Item` WHERE
									purchase_order = %(purchase_order)s AND docstatus <> 2""", {"purchase_order": self.name}, as_dict=True)
			has_pi = frappe.db.sql("""SELECT name FROM `tabPurchase Invoice Item` WHERE
									purchase_order = %(purchase_order)s AND docstatus <> 2""", {"purchase_order": self.name}, as_dict=True)
			if len(has_pr) == 0 and len(has_pi) == 0:
				self.set_onload("ais_allow_tax_edit", True)
			else:
				self.set_onload("ais_allow_tax_edit", False)

	def validate(self):
		super().validate()
		self.validate_case_pack_on_moq()

	def validate_case_pack_on_moq(self):
		for item in self.items:
			if not item.item_code:
				continue

			item_doc = frappe.get_doc("Item", item.item_code)

			if not item_doc.nat_enforce_case_pack_on_moq:
				continue

			min_order_qty = flt(item_doc.min_order_qty)
			if min_order_qty <= 0:
				continue

			# Ordered qty must be a positive multiple of the minimum order qty
			qty = flt(item.qty)
			if qty <= 0 or flt(qty % min_order_qty, item.precision("qty")) != 0:
				frappe.throw(_(
					"Row #{0}: Quantity for item {1} must be a multiple of the "
					"minimum order quantity ({2})."
				).format(item.idx, frappe.bold(item.item_code), min_order_qty))

	def on_workflow_action(self, workflow_action):
		if workflow_action == "Mark as Sent":
			frappe.db.set_value("Purchase Order", self.name, {
				"custom_sent_on": frappe.utils.now_datetime(),
				"custom_sent_by": frappe.session.user,
			})

	def before_submit(self):
		self.barcode_check()

	def barcode_check(self):
		for item in self.items:
			barcode_exists = frappe.db.exists("Item Barcode", {"parent": item.item_code})
			if not barcode_exists:
				frappe.throw(f"Error: Please add a barcode for item {item.item_code}")

@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def shipping_address_query(doctype, txt, searchfield, start, page_len, filters):
	link_doctype = filters.pop('link_doctype')
	link_name = filters.pop('link_name')
	company = filters.pop('company')
	return frappe.db.sql('''select
			`tabAddress`.name
		from
			`tabAddress`, `tabDynamic Link`
		where
			`tabDynamic Link`.parent = `tabAddress`.name and
			`tabDynamic Link`.parenttype = 'Address' and
			ifnull(`tabAddress`.disabled, 0) = 0 and
			(`tabDynamic Link`.link_doctype = %(link_doctype)s and
			`tabDynamic Link`.link_name = %(link_name)s)
			OR 
			(`tabDynamic Link`.link_doctype = 'Company' and
			`tabDynamic Link`.link_name = %(company)s and
			`tabAddress`.is_your_company_address = 1)''',
			{'link_name': link_name, 'link_doctype': link_doctype, 'company': company}
			)
			
@frappe.whitelist()
def get_po_items(docname):
	items = []
	added_items = []
	doc = frappe.get_doc('Purchase Order', docname)
	for item in doc.items:
		if item.item_code not in added_items:
			items.append(item)
			added_items.append(item.item_code)
		else:
			for i in items:
				if i.item_code == item.item_code:
					i.update({
						'qty': i.qty + item.qty
					})
	return items

# Metactical customizations: Edit the function to have the option to get all
# items with default supplier as supplier
@frappe.whitelist()
def make_purchase_order_based_on_supplier(source_name, target_doc=None, args=None):
	mr = source_name

	supplier_items = get_items_based_on_default_supplier(args.get("supplier"))
	
	material_requests = [mr]
	if args.get("get_all_items", False):
		material_requests = get_material_requests_based_on_items(supplier_items)

	def postprocess(source, target_doc):
		target_doc.supplier = args.get("supplier")
		if getdate(target_doc.schedule_date) < getdate(nowdate()):
			target_doc.schedule_date = None
		target_doc.set(
			"items",
			[
				d for d in target_doc.get("items") if d.get("item_code") in supplier_items and d.get("qty") > 0
			],
		)

		set_missing_values(source, target_doc)
	
	for mr in material_requests:
		target_doc = get_mapped_doc(
			"Material Request",
			mr,
			{
				"Material Request": {
					"doctype": "Purchase Order",
				},
				"Material Request Item": {
					"doctype": "Purchase Order Item",
					"field_map": [
						["name", "material_request_item"],
						["parent", "material_request"],
						["uom", "stock_uom"],
						["uom", "uom"],
					],
					"postprocess": update_item,
					"condition": lambda doc: doc.ordered_qty < doc.qty,
				},
			},
			target_doc,
			postprocess,
		)

	return target_doc
	
@frappe.whitelist()
def get_items_based_on_default_supplier(supplier):
	supplier_items = [
		d.parent
		for d in frappe.db.get_all(
			"Item Default", {"default_supplier": supplier, "parenttype": "Item"}, "parent"
		)
	]

	return supplier_items
	
# Metactical Customization: Get material requests based on default supplier
def get_material_requests_based_on_items(supplier_items):
	if not supplier_items:
		frappe.throw(_("The supplier is not the default supplier for any items."))

	material_requests = frappe.db.sql_list("""select distinct mr.name
		from `tabMaterial Request` mr, `tabMaterial Request Item` mr_item
		where mr.name = mr_item.parent
			and mr_item.item_code in (%s)
			and mr.material_request_type = 'Purchase'
			and mr.per_ordered < 99.99
			and mr.docstatus = 1
			and mr.status != 'Stopped'
		order by mr_item.item_code ASC""" % ', '.join(['%s']*len(supplier_items)),
		tuple(supplier_items))

	return material_requests


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_material_requests_based_on_supplier(doctype, txt, searchfield, start, page_len, filters):
	conditions = ""
	if txt:
		conditions += "and mr.name like '%%" + txt + "%%' "

	if filters.get("transaction_date"):
		date = filters.get("transaction_date")[1]
		conditions += "and mr.transaction_date between '{0}' and '{1}' ".format(date[0], date[1])

	supplier = filters.get("supplier")
	supplier_items = get_items_based_on_default_supplier(supplier)

	if not supplier_items:
		frappe.throw(_("{0} is not the default supplier for any items.").format(supplier))

	material_requests = frappe.db.sql(
		"""select distinct mr.name, transaction_date,company
		from `tabMaterial Request` mr, `tabMaterial Request Item` mr_item
		where mr.name = mr_item.parent
			and mr_item.item_code in ({0})
			and mr.material_request_type = 'Purchase'
			and mr.per_ordered < 99.99
			and mr.docstatus = 1
			and mr.status != 'Stopped'
			and mr.company = %s
			{1}
		order by mr_item.item_code ASC
		limit {2} offset {3} """.format(
			", ".join(["%s"] * len(supplier_items)), conditions, cint(page_len), cint(start)
		),
		tuple(supplier_items) + (filters.get("company"),),
		as_dict=1,
	)

	return material_requests
	
def set_missing_values(source, target_doc, for_validate=False):
	if target_doc.doctype == "Purchase Order" and getdate(target_doc.schedule_date) <  getdate(nowdate()):
		target_doc.schedule_date = None
	super(BuyingController, target_doc).set_missing_values(for_validate)

	target_doc.set_supplier_from_item_default()
	target_doc.set_price_list_currency("Buying")

	# Metactical Customization: Set contact and address details for supplier, if they are not mentioned
	if getattr(target_doc, "supplier", None):
		target_doc.update_if_missing(get_party_details(target_doc.supplier, party_type="Supplier", ignore_permissions=target_doc.flags.ignore_permissions,
		doctype=target_doc.doctype, company=target_doc.company, party_address=target_doc.supplier_address, shipping_address=target_doc.get('shipping_address')))
	target_doc.run_method("calculate_taxes_and_totals")
	
'''def set_missing_values(target_doc, for_validate=False):
		super(BuyingController, target_doc).set_missing_values(for_validate)

		target_doc.set_supplier_from_item_default()
		target_doc.set_price_list_currency("Buying")

		# set contact and address details for supplier, if they are not mentioned
		if getattr(target_doc, "supplier", None):
			target_doc.update_if_missing(get_party_details(target_doc.supplier, party_type="Supplier", ignore_permissions=target_doc.flags.ignore_permissions,
			doctype=target_doc.doctype, company=target_doc.company, party_address=target_doc.supplier_address, shipping_address=target_doc.get('shipping_address')))

		#self.set_missing_item_details(for_validate)
		return target_doc'''
		
def update_item(obj, target, source_parent):
	target.conversion_factor = obj.conversion_factor
	target.qty = flt(flt(obj.stock_qty) - flt(obj.ordered_qty))/ target.conversion_factor
	target.stock_qty = (target.qty * target.conversion_factor)
	if getdate(target.schedule_date) < getdate(nowdate()):
		target.schedule_date = None

@frappe.whitelist()
def get_default_supplier_address(name):
	supplier = frappe.db.exists("Supplier", name)
 
	if supplier:
		supplier = frappe.get_doc("Supplier", name)
		return supplier.nat_shipping_address, supplier.nat_billing_address
  
	return "", ""


@frappe.whitelist()
def get_party_details(*args, **kwargs):
	kwargs.pop("cmd", None)
	kwargs.pop("data", None)
	kwargs.pop("method", None)

	party_details = erpnext_get_party_details(*args, **kwargs)

	party_type = kwargs.get("party_type") or (len(args) > 2 and args[2]) or "Customer"
	doctype = kwargs.get("doctype") or (len(args) > 8 and args[8])
	party = kwargs.get("party") or (args[0] if args else None)
	ignore_permissions = kwargs.get("ignore_permissions", False)

	if party_type != "Supplier" or doctype != "Purchase Order" or not party:
		return party_details

	shipping_address, billing_address = get_default_supplier_address(party)
	billing_address = billing_address or ""
	shipping_address = shipping_address or ""

	party_details.update(
		billing_address=billing_address,
		billing_address_display=(
			render_address(billing_address, check_permissions=not ignore_permissions)
			if billing_address else ""
		),
		shipping_address=shipping_address,
		shipping_address_display=(
			render_address(shipping_address, check_permissions=not ignore_permissions)
			if shipping_address else ""
		),
	)

	if billing_address:
		party_details.update(get_fetch_values(doctype, "billing_address", billing_address))

	if shipping_address:
		party_details.update(get_fetch_values(doctype, "shipping_address", shipping_address))

	party_details["tax_category"] = get_address_tax_category(
		party_details.get("tax_category"),
		billing_address or None,
		shipping_address or None,
	)

	return party_details


@frappe.whitelist()
def get_billing_shipping_address(supplier_name):
	shipping_address, billing_address = get_default_supplier_address(supplier_name)

	return {"shipping_address": shipping_address, "billing_address": billing_address}


@frappe.whitelist()
def make_inbound_shipment(source_name, target_doc=None):
	def set_missing_values(source, target):
		target.source_type = "Manual"

	def update_item(obj, target, source_parent):
		target.shipped_qty = flt(obj.qty) - flt(obj.received_qty)

	doc = get_mapped_doc(
		"Purchase Order",
		source_name,
		{
			"Purchase Order": {
				"doctype": "Inbound Shipment",
				"field_map": {"name": "purchase_order"},
				"validation": {
					"docstatus": ["=", 1],
				},
			},
			"Purchase Order Item": {
				"doctype": "Inbound Shipment Item",
				"field_map": {
					"name": "po_detail",
				},
				"postprocess": update_item,
				"condition": lambda doc: abs(doc.received_qty) < abs(doc.qty),
			},
		},
		target_doc,
		set_missing_values,
	)

	return doc