import frappe
from erpnext.controllers.buying_controller import BuyingController
from six import string_types
from frappe.model.mapper import get_mapped_doc
from frappe import msgprint, _
from frappe.utils import cstr, flt, getdate, new_line_sep, nowdate, add_days
from erpnext.accounts.party import get_party_details
from erpnext.buying.doctype.purchase_order.purchase_order import PurchaseOrder
from frappe.utils import flt, cstr, now, get_datetime_str, file_lock, date_diff, now_datetime
from frappe import _, msgprint, is_whitelisted

class CustomPurchaseOrder(PurchaseOrder):
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
	
	def submit(self):
		if len(self.items) > 100:
			msgprint(
				_(
					"The task has been enqueued as a background job. In case there is any issue on processing in background, the system will add a comment about the error on this Stock Reconciliation and revert to the Draft stage"
				)
			)
			self.queue_action("submit", timeout=2000)
		else:
			self._submit()
	
	def queue_action(self, action, **kwargs):
		"""Run an action in background. If the action has an inner function,
		like _submit for submit, it will call that instead"""
		# call _submit instead of submit, so you can override submit to call
		# run_delayed based on some action
		# See: Stock Reconciliation
		from frappe.utils.background_jobs import enqueue

		if hasattr(self, '_' + action):
			action = '_' + action

		if file_lock.lock_exists(self.get_signature()):
			frappe.throw(_('This document is currently queued for execution. Please try again'),
				title=_('Document Queued'))
		
		frappe.db.set_value(self.doctype, self.name, 'ais_queue_status', 'Queued',  update_modified=False)
		frappe.db.set_value(self.doctype, self.name, 'ais_queued_date', now_datetime(),  update_modified=False)
		frappe.db.set_value(self.doctype, self.name, 'ais_queued_by', frappe.session.user,  update_modified=False)
		self.lock()
		enqueue('metactical.custom_scripts.frappe.document.execute_action', doctype=self.doctype, name=self.name,
			action=action, **kwargs)

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
	
@frappe.whitelist()
def make_purchase_order_based_on_supplier(source_name, target_doc=None):
	if target_doc:
		if isinstance(target_doc, string_types):
			import json
			target_doc = frappe.get_doc(json.loads(target_doc))
		target_doc.set("items", [])

	material_requests, supplier_items = get_material_requests_based_on_supplier(source_name)

	def postprocess(source, target_doc):
		target_doc.supplier = source_name
		if getdate(target_doc.schedule_date) < getdate(nowdate()):
			target_doc.schedule_date = None
		target_doc.set("items", [d for d in target_doc.get("items")
			if d.get("item_code") in supplier_items and d.get("qty") > 0])

		set_missing_values(source, target_doc)

	for mr in material_requests:
		target_doc = get_mapped_doc("Material Request", mr, 	{
			"Material Request": {
				"doctype": "Purchase Order",
			},
			"Material Request Item": {
				"doctype": "Purchase Order Item",
				"field_map": [
					["name", "material_request_item"],
					["parent", "material_request"],
					["uom", "stock_uom"],
					["uom", "uom"]
				],
				"postprocess": update_item,
				"condition": lambda doc: doc.ordered_qty < doc.qty
			}
		}, target_doc, postprocess)

	return target_doc

def get_material_requests_based_on_supplier(supplier):
	supplier_items = [d.parent for d in frappe.db.get_all("Item Default",
		{"default_supplier": supplier}, 'parent')]
	if not supplier_items:
		frappe.throw(_("{0} is not the default supplier for any items.".format(supplier)))

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

	return material_requests, supplier_items
	
def set_missing_values(source, target_doc, for_validate=False):
	if target_doc.doctype == "Purchase Order" and getdate(target_doc.schedule_date) <  getdate(nowdate()):
		target_doc.schedule_date = None
	super(BuyingController, target_doc).set_missing_values(for_validate)

	target_doc.set_supplier_from_item_default()
	target_doc.set_price_list_currency("Buying")

	# set contact and address details for supplier, if they are not mentioned
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
