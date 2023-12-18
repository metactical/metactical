import frappe
from frappe import _
import barcode as _barcode
from io import BytesIO
from frappe.model.mapper import get_mapped_doc, map_child_doc
from frappe.utils import nowdate, cstr, flt, cint, now, getdate
from erpnext.setup.doctype.company.company import update_company_current_month_sales
from erpnext.accounts.doctype.sales_invoice.sales_invoice import unlink_inter_company_doc
from erpnext.healthcare.utils import manage_invoice_submit_cancel
from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice
from erpnext.controllers.accounts_controller import AccountsController

class CustomSalesInvoice(SalesInvoice):
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
		
	def validate_pos(self):
		if self.is_return:
			return
			
	def calculate_paid_amount(self):

		paid_amount = base_paid_amount = 0.0
		
		if self.doc.is_return:
			self.doc.set("payments", [])
		elif self.doc.is_pos:
			for payment in self.doc.get("payments"):
				payment.amount = flt(payment.amount)
				payment.base_amount = payment.amount * flt(self.doc.conversion_rate)
				paid_amount += payment.amount
				base_paid_amount += payment.base_amount
		elif not self.doc.is_return:
			self.doc.set("payments", [])

		if self.doc.redeem_loyalty_points and self.doc.loyalty_amount:
			base_paid_amount += self.doc.loyalty_amount
			paid_amount += self.doc.loyalty_amount / flt(self.doc.conversion_rate)

		self.doc.paid_amount = flt(paid_amount, self.doc.precision("paid_amount"))
		self.doc.base_paid_amount = flt(base_paid_amount, self.doc.precision("base_paid_amount"))
		
	def set_total_amount_to_default_mop(self, total_amount_to_pay):
		if self.doc.get("is_return"):
			self.doc.payments = []
			return
			
		total_paid_amount = 0
		for payment in self.doc.get("payments"):
			total_paid_amount += (
				payment.amount if self.doc.party_account_currency == self.doc.currency else payment.base_amount
			)

		pending_amount = total_amount_to_pay - total_paid_amount

		if pending_amount > 0:
			default_mode_of_payment = frappe.db.get_value(
				"POS Payment Method",
				{"parent": self.doc.pos_profile, "default": 1},
				["mode_of_payment"],
				as_dict=1,
			)

			if default_mode_of_payment:
				self.doc.payments = []
				self.doc.append(
					"payments",
					{
						"mode_of_payment": default_mode_of_payment.mode_of_payment,
						"amount": pending_amount,
						"default": 1,
					},
				)
				
	def validate_pos_paid_amount(self):
		if len(self.payments) == 0 and self.is_pos and not self.is_return:
			frappe.throw(_("At least one mode of payment is required for POS invoice."))

	

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
