import frappe
import functools
from frappe import _, msgprint
import barcode as _barcode
from io import BytesIO
from frappe.model.mapper import get_mapped_doc, map_child_doc
from frappe.utils import nowdate, cstr, flt, cint, now, getdate
from erpnext.setup.doctype.company.company import update_company_current_month_sales
from erpnext.accounts.doctype.sales_invoice.sales_invoice import unlink_inter_company_doc
from erpnext.healthcare.utils import manage_invoice_submit_cancel
from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice
from erpnext.controllers.selling_controller import SellingController
from erpnext.controllers.stock_controller import StockController
from erpnext.controllers.accounts_controller import AccountsController
from metactical.custom_scripts.utils.metactical_utils import queue_action

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
	remove_ref_doc_link_from_pe(ref_doc.doctype, ref_doc.name, multiple_orders, ref_doc.items[0].sales_order)

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

def remove_ref_doc_link_from_pe(ref_type, ref_no, multiple_orders, sales_order=None):
	if multiple_orders == False:
		linked_pe = frappe.db.sql_list("""select parent from `tabPayment Entry Reference`
			where reference_doctype=%s and reference_name=%s and docstatus < 2""", (ref_type, ref_no))

		if linked_pe:
			frappe.db.sql("""update `tabPayment Entry Reference`
				set modified=%s, modified_by=%s, reference_doctype='Sales Order', reference_name=%s
				where reference_doctype=%s and reference_name=%s
				and docstatus < 2""", (now(), frappe.session.user, sales_order, ref_type, ref_no))

			for pe in linked_pe:
				pe_doc = frappe.get_doc("Payment Entry", pe)
				pe_doc.set_total_allocated_amount()
				pe_doc.set_unallocated_amount()
				pe_doc.clear_unallocated_reference_document_rows()

				frappe.db.sql("""update `tabPayment Entry` set total_allocated_amount=%s,
					base_total_allocated_amount=%s, unallocated_amount=%s, modified=%s, modified_by=%s
					where name=%s""", (pe_doc.total_allocated_amount, pe_doc.base_total_allocated_amount,
						pe_doc.unallocated_amount, now(), frappe.session.user, pe))

			frappe.msgprint(_("Payment Entries {0} are re-linked to Sales Order {1}".format("\n".join(linked_pe), sales_order)))
	else:
		linked_pe = frappe.db.sql_list(
			"""select parent from `tabPayment Entry Reference`
			where reference_doctype=%s and reference_name=%s and docstatus < 2""",
			(ref_type, ref_no),
		)

		if linked_pe:
			frappe.db.sql(
				"""update `tabPayment Entry Reference`
				set allocated_amount=0, modified=%s, modified_by=%s
				where reference_doctype=%s and reference_name=%s
				and docstatus < 2""",
				(now(), frappe.session.user, ref_type, ref_no),
			)

			for pe in linked_pe:
				try:
					pe_doc = frappe.get_doc("Payment Entry", pe)
					pe_doc.set_amounts()
					pe_doc.clear_unallocated_reference_document_rows()
					pe_doc.validate_payment_type_with_outstanding()
				except Exception as e:
					msg = _("There were issues unlinking payment entry {0}.").format(pe_doc.name)
					msg += "<br>"
					msg += _("Please cancel payment entry manually first")
					frappe.throw(msg, exc=PaymentEntryUnlinkError, title=_("Payment Unlink Error"))

				frappe.db.sql(
					"""update `tabPayment Entry` set total_allocated_amount=%s,
					base_total_allocated_amount=%s, unallocated_amount=%s, modified=%s, modified_by=%s
					where name=%s""",
					(
						pe_doc.total_allocated_amount,
						pe_doc.base_total_allocated_amount,
						pe_doc.unallocated_amount,
						now(),
						frappe.session.user,
						pe,
					),
				)

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