import frappe
import functools
from frappe import _, msgprint
import barcode as _barcode
from io import BytesIO
from frappe.utils import now
from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice
from erpnext.controllers.selling_controller import SellingController
from erpnext.controllers.stock_controller import StockController
from erpnext.controllers.accounts_controller import AccountsController
from metactical.custom_scripts.utils.metactical_utils import queue_action, check_si_payment_status_for_so
from erpnext.accounts.utils import convert_to_list

class CustomSalesInvoice(SalesInvoice, SellingController, StockController, AccountsController):
	def on_cancel(self):
		# Metactical Customization: Relink payment entries to sales orders when sales invoice is cancelled
		if self.doctype in ["Sales Invoice", "Purchase Invoice"]:
			if frappe.db.get_single_value("Accounts Settings", "unlink_payment_on_cancellation_of_invoice"):
				unlink_ref_doc_from_payment_entries(self)

			elif self.doctype in ["Sales Order", "Purchase Order"]:
				if frappe.db.get_single_value(
					"Accounts Settings", "unlink_advance_payment_on_cancelation_of_order"
				):
					unlink_ref_doc_from_payment_entries(self)

				if self.doctype == "Sales Order":
					self.unlink_ref_doc_from_po()
		super(CustomSalesInvoice, self).on_cancel()
		
	def before_save(self):
		super(CustomSalesInvoice, self).before_save()
		#Metactical Customization: Add barcode to Sales Invoice
		rv = BytesIO()
		_barcode.get('code128', self.name).write(rv)
		bstring = rv.getvalue()
		self.ais_barcode = bstring.decode('ISO-8859-1')
		self.check_pay_with_store_credit()

	def check_pay_with_store_credit(self):
		if self.neb_pay_with_store_credit and not self.advances:
			self.neb_pay_with_store_credit = 0
			frappe.msgprint(f"Customer <b>{self.customer}</b> does not have store credit to pay this invoice.")
		
		store_credit_account = get_store_credit_account(self.currency)
		if self.neb_pay_with_store_credit:
			if store_credit_account:
				if store_credit_account != self.debit_to:
					self.debit_to = store_credit_account
					self.set_missing_values()
			else:
				self.neb_pay_with_store_credit = 0
				frappe.msgprint(f"Store credit account not set for <b>{self.currency}</b> currency in Metactical Settings.")

	def calculate_taxes_and_totals(self):
		from metactical.custom_scripts.controllers.taxes_and_totals import custom_calculate_taxes_and_totals
		custom_calculate_taxes_and_totals(self)

		if self.doctype in (
			"Sales Order",
			"Delivery Note",
			"Sales Invoice",
			"POS Invoice",
		):
			self.calculate_commission()
			self.calculate_contribution()

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

	def set_status(self, update=False, status=None, update_modified=True):
		super(CustomSalesInvoice, self).set_status(update, status, update_modified)
		
		# Metactical Customization: Added
		if self.status == "Paid" and not self.neb_payment_completed_at:
			self.db_set("neb_payment_completed_at", frappe.utils.getdate(now()), notify=True)
			
			# Metactical Customization: Check if all invoices for the sales order are paid and update sales order
			sales_orders = []
			for row in self.items:
				if row.sales_order and row.sales_order not in sales_orders:
					sales_orders.append(row.sales_order)
			
			for sales_order in sales_orders:
				billing_status = frappe.db.get_value("Sales Order", sales_order, "billing_status")
				if billing_status == "Fully Billed":
					all_invoices_paid = check_si_payment_status_for_so(sales_order)
					if all_invoices_paid:
						frappe.db.set_value("Sales Order", sales_order, "neb_payment_completed_at", frappe.utils.getdate(now()), update_modified=True)
		elif self.status != "Paid" and self.neb_payment_completed_at:
			self.db_set("neb_payment_completed_at", None, notify=True)

def unlink_ref_doc_from_payment_entries(ref_doc):	
	#Check for sales order
	multiple_orders = False
	items = ref_doc.get('items')
	sales_order = items[0].get('sales_order')
	for row in items:
		if row.get('sales_order') is None or row.get('sales_order') != sales_order:
			multiple_orders = True
			break
		
	
	remove_ref_doc_link_from_jv(ref_doc.doctype, ref_doc.name, multiple_orders, ref_doc.items[0].sales_order)
	remove_ref_doc_link_from_pe(ref_doc.doctype, ref_doc.name, None, multiple_orders, ref_doc.items[0].sales_order)

	if multiple_orders == False:
		frappe.db.sql("""update `tabGL Entry`
			set against_voucher_type='Sales Order', against_voucher=%s,
			modified=%s, modified_by=%s
			where against_voucher_type=%s and against_voucher=%s
			and voucher_no != ifnull(against_voucher, '')""",
			(ref_doc.items[0].sales_order, now(), frappe.session.user, ref_doc.doctype, ref_doc.name))
	else:
		frappe.db.sql("""update `tabGL Entry`
			set against_voucher_type=null, against_voucher=null,
			modified=%s, modified_by=%s
			where against_voucher_type=%s and against_voucher=%s
			and voucher_no != ifnull(against_voucher, '')""",
			(now(), frappe.session.user, ref_doc.doctype, ref_doc.name))

	if ref_doc.doctype in ("Sales Invoice", "Purchase Invoice"):
		ref_doc.set("advances", [])

		frappe.db.sql(
			"""delete from `tab{0} Advance` where parent = %s""".format(ref_doc.doctype), ref_doc.name
		)

def remove_ref_doc_link_from_jv(ref_type, ref_no, multiple_orders, sales_order=None):
	linked_jv = frappe.db.sql_list("""select parent from `tabJournal Entry Account`
		where reference_type=%s and reference_name=%s and docstatus < 2""", (ref_type, ref_no))

	if linked_jv:
		frappe.db.sql("""update `tabJournal Entry Account`
			set reference_type=null, reference_name = null,
			modified=%s, modified_by=%s
			where reference_type=%s and reference_name=%s
			and docstatus < 2""", (now(), frappe.session.user, ref_type, ref_no))

		frappe.msgprint(_("Journal Entries {0} are un-linked".format("\n".join(linked_jv))))

def remove_ref_doc_link_from_pe(
	ref_type: str | None = None, ref_no: str | None = None, payment_name: str | None = None, multiple_orders=True, sales_order=None
):
	per = qb.DocType("Payment Entry Reference")
	pay = qb.DocType("Payment Entry")

	linked_pe = (
		qb.from_(per)
		.select(per.parent)
		.where((per.reference_doctype == ref_type) & (per.reference_name == ref_no) & (per.docstatus.lt(2)))
		.run(as_list=1)
	)
	linked_pe = convert_to_list(linked_pe)
	# remove reference only from specified payment
	linked_pe = [x for x in linked_pe if x == payment_name] if payment_name else linked_pe

	if linked_pe:
		# Metactical Customization: Relink sales invoices to sales orders
		if not multiple_orders and sales_order is not None:
			update_query = (
				qb.update(per)
				.set(per.reference_doctype, 'Sales Order')
				.set(per.reference_name, sales_order)
				.set(per.modified, now())
				.set(per.modified_by, frappe.session.user)
				.where(per.docstatus.lt(2) & (per.reference_doctype == ref_type) & (per.reference_name == ref_no))
			)

			if payment_name:
				update_query = update_query.where(per.parent == payment_name)

			update_query.run()
		else:
			update_query = (
				qb.update(per)
				.set(per.allocated_amount, 0)
				.set(per.modified, now())
				.set(per.modified_by, frappe.session.user)
				.where(per.docstatus.lt(2) & (per.reference_doctype == ref_type) & (per.reference_name == ref_no))
			)

			if payment_name:
				update_query = update_query.where(per.parent == payment_name)

			update_query.run()

		for pe in linked_pe:
			try:
				pe_doc = frappe.get_doc("Payment Entry", pe)
				pe_doc.set_amounts()
				pe_doc.clear_unallocated_reference_document_rows()
				pe_doc.validate_payment_type_with_outstanding()
			except Exception:
				msg = _("There were issues unlinking payment entry {0}.").format(pe_doc.name)
				msg += "<br>"
				msg += _("Please cancel payment entry manually first")
				frappe.throw(msg, exc=PaymentEntryUnlinkError, title=_("Payment Unlink Error"))

			qb.update(pay).set(pay.total_allocated_amount, pe_doc.total_allocated_amount).set(
				pay.base_total_allocated_amount, pe_doc.base_total_allocated_amount
			).set(pay.unallocated_amount, pe_doc.unallocated_amount).set(pay.modified, now()).set(
				pay.modified_by, frappe.session.user
			).where(pay.name == pe).run()

		frappe.msgprint(_("Payment Entries {0} are un-linked").format("\n".join(linked_pe)))

@frappe.whitelist()
def create_journal_entry(source_name, bank_cash, amount, purpose, target_doc=None):
	def update_accounts(source_doc, target_doc):
		amount_after_tax = float(amount)
		target_doc.accounts = []
		if purpose == "Create Credit Note and Refund Customer":
			#Add taxes and charges
			for row in source_doc.taxes:
				tax_amount = (float(amount) * float(row.rate))/100
				amount_after_tax = amount_after_tax - tax_amount
				account = frappe.new_doc('Journal Entry Account')
				account.update({
					"account": row.account_head,
					"cost_center": source_doc.items[0].cost_center,
					"project": source_doc.items[0].project,
					"debit_in_account_currency": tax_amount
				})
				target_doc.append("accounts", account)
				
			#For the simplest implementation, we assume all items on the invoice share the same income account
			account = frappe.new_doc('Journal Entry Account')
			account.update({
				"account": source_doc.items[0].income_account,
				"cost_center": source_doc.items[0].cost_center,
				"project": source_doc.items[0].project,
				"debit_in_account_currency": amount_after_tax
			})
			target_doc.append("accounts", account)
			
			account = frappe.new_doc('Journal Entry Account')
			account.update({
				"account": source_doc.debit_to,
				"reference_type": "Sales Invoice",
				"party_type": "Customer",
				"party": source_doc.customer,
				"reference_name": source_name,
				"credit_in_account_currency": amount
			})
			target_doc.append("accounts", account)
			
			account = frappe.new_doc('Journal Entry Account')
			account.update({
				"account": source_doc.debit_to,
				"reference_type": "Sales Invoice",
				"party_type": "Customer",
				"party": source_doc.customer,
				"reference_name": source_name,
				"debit_in_account_currency": amount
			})
			target_doc.append("accounts", account)
		else:
			account = frappe.new_doc('Journal Entry Account')
			account.update({
				"account": source_doc.debit_to,
				"debit_in_account_currency": amount,
				"party_type": "Customer",
				"party": source_doc.customer,
			})
			target_doc.append("accounts", account)
			
			#If Sales Order entered, then assume advance payment made against Sales Order
			if source_doc.items[0].sales_order:
				target_doc.update({
					"ais_sales_order": source_doc.items[0].sales_order
				})
	
		#For all purposes, add bank/cash account
		account = frappe.new_doc('Journal Entry Account')
		account.update({
			"account": bank_cash,
			"credit_in_account_currency": amount
		})
		target_doc.append("accounts", account)

	target_doc = frappe.new_doc('Journal Entry')
	target_doc.update({
		"voucher_type": "Credit Note"
	})
	source_doc = frappe.get_doc('Sales Invoice', source_name)
	update_accounts(source_doc, target_doc)
	return target_doc

# Metactical Customization: Get mode of payment for the print format		
@frappe.whitelist()
def si_mode_of_payment(name):
	payment_mode = ''
	mode = frappe.db.sql("""SELECT
								pe.mode_of_payment
							FROM
								`tabPayment Entry Reference` per
							LEFT JOIN
								`tabPayment Entry` pe ON pe.name = per.parent
							WHERE
								per.reference_doctype = 'Sales Invoice' AND per.reference_name = %(name)s
								AND pe.docstatus = 1""", {'name': name}, as_dict=1)
	if len(mode) > 0:
		payment_mode = mode[0].mode_of_payment
	return payment_mode

def get_commercial_invoice(doc):
	doc.mode_of_payment = si_mode_of_payment(doc.name)

	sales_order = ""
	for item in doc.items:
		if item.against_sales_order:
			sales_order = item.against_sales_order
			break
	
	if sales_order:
		sales_order = frappe.get_doc("Sales Order", sales_order)
		doc.delivery_date = sales_order.delivery_date

	address = get_customer_address(sales_order.customer)
	customer_phone, customer_email = get_customer_contact(sales_order.customer)

	billing_address = address["Billing"] if "Billing" in address else None
	shipping_address = address["Shipping"] if "Shipping" in address else None
	sales_orders = []

	packing_slips = frappe.db.get_list("Packing Slip", filters={"delivery_note": doc.name, "docstatus":1}, order_by= "from_case_no asc", fields=["name", "from_case_no"])
	packing_slip_names = [ps.name for ps in packing_slips]
	
	# group dn items by item_code
	dn_items_dict = {}
	for item in doc.items:
		if item.item_code not in dn_items_dict:
			dn_items_dict[item.item_code] = []
		dn_items_dict[item.item_code].append(item)


	items_list = []
	items_with_no_template = []

	for ps in packing_slips:
		items = {}
		packing_slip_items = frappe.db.get_list("Packing Slip Item", 
													filters={"parent": ps.name}, 
													fields=["name", "item_code", "item_name", "weight_uom", "net_weight", "qty", "parent"])

		for psi in packing_slip_items:
			psi.rate = dn_items_dict[psi.item_code][0].rate if psi.item_code in dn_items_dict else 0
			for ps in packing_slips:
				if psi.parent == ps.name:
					psi.from_case_no = ps.from_case_no

			item_detail = frappe.db.get_value("Item", psi.item_code, ["variant_of", "country_of_origin"], as_dict=True)
			psi.country_of_origin = frappe.db.get_value("Country", item_detail.country_of_origin, "code").upper() if item_detail.country_of_origin else "-"
			# if item_detail.variant_of:
			# 	template_name = frappe.db.get_value("Item", item_detail.variant_of, "item_name")
			# 	if template_name:
			# 		psi.template_name = template_name

			# 	psi.variant_of = item_detail.variant_of
			# else:
			psi.variant_of = "No Template"
			psi.template_name = ""
		
		# group items based on variant of 
		for item in packing_slip_items:
			if item.variant_of != "No Template":
				if item.variant_of not in items:
					items[item.variant_of] = []
				items[item.variant_of].append(item)
			else:
				items_with_no_template.append(item)
		
		items_list.append(items)
	items_list.append({"No Template": items_with_no_template})

	order_numbers = 1
	sales_orders = [sales_order.name]
	
	# get tracking number
	tracking_number, shipments = get_tracking_number(sales_orders)
	tracking_number = ', '.join(tracking_number) if tracking_number else "-"

	# get customer POs
	customer_pos = ""
	customer_pos = get_customer_po(sales_orders)
	customer_pos = ', '.join(customer_pos) if customer_pos else "-"

	# get freight terms
	freight_term = get_freight_terms(shipments)
	freight_term = freight_term.split(" ")[0] if freight_term else "-"

	# get sales person
	sales_person = get_sales_person(sales_orders)
	sales_person = ', '.join(sales_person) if sales_person else "-"

	html = frappe.render_template("metactical/metactical/print_format/ci___export___v1/ci_export_v1.html", 
									{	
										"items_list": items_list,
										"doc": doc, 
										"ship_via": "-",
										"sold_to": billing_address, 
										"shipped_to": shipping_address,
										"order_numbers": order_numbers ,
										"tracking_number": tracking_number,
										"customer_pos": customer_pos,
										"freight_terms": freight_term,
										"sales_person": sales_person,
										"customer_phone": customer_phone if customer_phone else "-",
										"customer_email": customer_email if customer_email else "-",
									}
								)
	return html

def get_rate(packing_slip_item, delivery_note):

	# add rate to packing slip items from delivery note items
	if psi.item_code in dn_items_dict:
		for item in dn_items_dict[psi.item_code]:
			psi.rate = item.rate
			psi.item_name = item.item_name
			psi.description = item.description

	return packing_slip_items

def get_customer_address(customer):
	customer_addresses = {}
	
	customer_address = frappe.db.sql("""select 	`tabAddress`.address_line1, 
												`tabAddress`.address_line2, 
												`tabAddress`.city, 
												`tabAddress`.state, 
												`tabAddress`.pincode, 
												`tabAddress`.country, 
												`tabAddress`.address_type
											from `tabAddress` 
											join `tabDynamic Link` on `tabAddress`.name = `tabDynamic Link`.parent
											where `tabDynamic Link`.link_doctype = 'Customer' and 
												  `tabDynamic Link`.link_name = %(customer)s""", 
											{'customer': customer}, as_dict=1)

	if len(customer_address) > 0:
		for address in customer_address:
			customer_info = frappe.db.get_value("Customer", customer, ["first_name", "last_name", "ais_company"])
			
			first_name = ""
			last_name = ""
			company = ""

			if customer_info:
				first_name = customer_info[0]
				last_name = customer_info[1]
				company = customer_info[2]

			address.first_name = first_name
			address.last_name = last_name
			address.company = company
			customer_addresses[address.address_type] = address
	
	return customer_addresses

def get_customer_contact(customer):
	contacts_list = frappe.db.sql("""select ce.email_id, cp.phone
								from `tabContact` c
								JOIN `tabContact Phone` cp on cp.parent=c.name
								LEFT JOIN `tabContact Email` ce on ce.parent=c.name
								INNER JOIN `tabDynamic Link` dl on dl.parent=c.name
								INNER Join `tabCustomer` cs on dl.link_name=cs.name
								where  dl.link_doctype="Customer" and 
									   dl.link_name = %(customer)s
								""", {'customer': customer}, as_dict=1)
	
	phone = ""
	email = ""

	if len(contacts_list) > 0:
		phone = contacts_list[0].phone
		email = contacts_list[0].email_id

	return phone, email

# Metactical Customization: Get tracking number for the print format
def get_tracking_number(sales_orders):
	tracking_numbers = []
	shipments = []

	delivery_note_items = frappe.db.get_list("Delivery Note Item", filters={"against_sales_order": ["in", sales_orders], "parenttype": "Delivery Note", "docstatus": 1}, fields=["parent"])
	# get delivery notes without duplicates
	delivery_notes = list(set([item.parent for item in delivery_note_items]))


	if delivery_notes:
		shipment_delivery_note = frappe.db.get_list("Shipment Delivery Note", filters={"delivery_note": ["in", delivery_notes], "docstatus": 1}, fields=["parent"], order_by="creation")
		shipments = [item.parent for item in shipment_delivery_note]
		
		# get shipments without duplicates
		shipments = list(set(shipments))

		if shipments:
			for shipment in shipments:
				shipment_doc = frappe.get_doc("Shipment", shipment)
				multiple_shipments = shipment_doc.shipments
				for shipment in multiple_shipments:
					if shipment.awb_number not in tracking_numbers:
						tracking_numbers.append(shipment.awb_number)

	return tracking_numbers, shipments

def get_customer_po(sales_orders):
	customer_po = []
	for sales_order in sales_orders:
		po_no = frappe.db.get_value("Sales Order", sales_order, "po_no")
		if po_no:
			customer_po.append(po_no)

	return customer_po

def get_freight_terms(shipments):
	freight_terms = ""
	if shipments:
		for shipment in shipments:
			incoterm = frappe.db.get_value("Shipment", shipment, "incoterm")
			if incoterm:
				freight_terms = incoterm
				break
	return freight_terms

def get_sales_person(sales_orders):
	sales_persons_list = []
	sales_persons = frappe.db.get_list("Sales Team", filters={"parent": ["in", sales_orders], "parenttype": "Sales Order"}, fields=["sales_person"])
	if sales_persons:
		sales_persons_list = [item.sales_person for item in sales_persons]

	return sales_persons_list
		
def get_totals(items):
	total_qty = 0
	total_amount = 0
	total_weight = 0
	variant_items = ""
	from_case_no = 0
	template_name = ""
	rate = 0
	country_of_origin = ""

	for item in items:
		variant_items += str(item.qty) +" / "+item.item_code+ "  "
		total_qty += item.qty
		total_amount += item.rate * item.qty
		total_weight += item.net_weight
		rate = item.rate

		if not from_case_no:
			from_case_no = item.from_case_no
		
		if not template_name:
			template_name = item.template_name

		if not country_of_origin and item.country_of_origin:
			country_of_origin = frappe.db.get_value("Country", item.country_of_origin, "code").upper()
	
	return {
		"total_qty": total_qty,
		"total_amount": total_amount,
		"total_weight": total_weight,
		"items": variant_items,
		"from_case_no": from_case_no,
		"template_name": template_name,
		"rate": rate,
		"country_of_origin": country_of_origin
	}

@frappe.whitelist()
def get_store_credit_account(currency):
	field = None
	if currency == 'CAD':
		field = "store_credit_account_cad"
	elif currency == 'USD':
		field = "store_credit_account_usd"

	if field:
		account = frappe.db.get_single_value("Metactical Settings", field)
		return account
	else:
		return None

@frappe.whitelist()
def get_customer_info(doc):
	if doc.neb_store_credit_beneficiary:
		customer = frappe.get_doc("Customer", doc.neb_store_credit_beneficiary)
		address = load_address(customer)
		contact = load_contact(customer)

		return {
			"contact": contact[0] if len(contact) > 0 else {},
			"address": address[0] if len(address) > 0 else {}
		}


def load_address(doc, key=None):
	"""Loads address list and contact list in `__onload`"""
	from frappe.contacts.doctype.address.address import get_address_display, get_condensed_address

	filters = [
		["Dynamic Link", "link_doctype", "=", doc.doctype],
		["Dynamic Link", "link_name", "=", doc.name],
		["Dynamic Link", "parenttype", "=", "Address"],
	]
	address_list = frappe.get_list("Address", 
									filters=filters, 
									fields=["city", "county", "state", "country", "pincode", "creation", "modified", "address_line1"], 
									order_by="creation desc")
	address_list = [a.update({"display": get_address_display(a)}) for a in address_list]

	address_list = sorted(
		address_list,
		key=functools.cmp_to_key(
			lambda a, b: (int(a.is_primary_address - b.is_primary_address))
			or (1 if a.modified - b.modified else 0)
		),
		reverse=True,
	)

	return address_list

def load_contact(doc):
	contact_list = []
	filters = [
		["Dynamic Link", "link_doctype", "=", doc.doctype],
		["Dynamic Link", "link_name", "=", doc.name],
		["Dynamic Link", "parenttype", "=", "Contact"],
	]
	contact_list = frappe.get_all("Contact", filters=filters, fields=["email_id", "phone", "mobile_no"])
	return contact_list