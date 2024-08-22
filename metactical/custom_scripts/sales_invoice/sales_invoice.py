import frappe
from frappe import _, msgprint, qb, throw
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
