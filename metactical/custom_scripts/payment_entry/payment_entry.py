import frappe
from erpnext.accounts.doctype.bank_account.bank_account import get_party_bank_account, get_bank_account_details
from erpnext.controllers.accounts_controller import AccountsController, get_supplier_block_status
from erpnext.accounts.doctype.invoice_discounting.invoice_discounting import get_party_account_based_on_invoice_discounting
from erpnext.accounts.utils import get_outstanding_invoices, get_account_currency, get_balance_on
from erpnext.accounts.party import get_party_account
from erpnext.accounts.doctype.journal_entry.journal_entry import get_default_bank_cash_account
from frappe.utils import flt, comma_or, nowdate, getdate
from frappe import _, scrub, ValidationError
from erpnext.accounts.doctype.payment_entry.payment_entry import get_reference_as_per_payment_terms
from metactical.custom_scripts.usaepay.usaepay_api import (
	get_card_token, 
	get_token_hash, 
	get_usaepay_transaction_detail, 
	refund_payment, 
	adjust_payment,
	get_usaepay_roles,
	void_payment_in_usaepay
)

@frappe.whitelist()
def get_payment_entry(dt, dn, party_amount=None, bank_account=None, bank_amount=None):
	doc = frappe.get_doc(dt, dn)
	if dt in ("Sales Order", "Purchase Order") and flt(doc.per_billed, 2) > 0:
		frappe.throw(_("Can only make payment against unbilled {0}").format(dt))

	if dt in ("Sales Invoice", "Sales Order"):
		party_type = "Customer"
	elif dt in ("Purchase Invoice", "Purchase Order"):
		party_type = "Supplier"
	elif dt in ("Expense Claim", "Employee Advance"):
		party_type = "Employee"
	elif dt in ("Fees"):
		party_type = "Student"

	# party account
	if dt == "Sales Invoice":
		party_account = get_party_account_based_on_invoice_discounting(dn) or doc.debit_to
	elif dt == "Purchase Invoice":
		party_account = doc.credit_to
	elif dt == "Fees":
		party_account = doc.receivable_account
	elif dt == "Employee Advance":
		party_account = doc.advance_account
	elif dt == "Expense Claim":
		party_account = doc.payable_account
	else:
		party_account = get_party_account(party_type, doc.get(party_type.lower()), doc.company)

	if dt not in ("Sales Invoice", "Purchase Invoice"):
		party_account_currency = get_account_currency(party_account)
	else:
		party_account_currency = doc.get("party_account_currency") or get_account_currency(party_account)

	# payment type
	if (dt == "Sales Order" or (dt in ("Sales Invoice", "Fees") and doc.outstanding_amount > 0)) \
		or (dt=="Purchase Invoice" and doc.outstanding_amount < 0):
			payment_type = "Receive"
	else:
		payment_type = "Pay"

	# amounts
	grand_total = outstanding_amount = exchange_rate = 0
	if party_amount:
		grand_total = outstanding_amount = party_amount
	elif dt in ("Sales Invoice", "Purchase Invoice"):
		if party_account_currency == doc.company_currency:
			grand_total = doc.base_rounded_total or doc.base_grand_total
		else:
			grand_total = doc.rounded_total or doc.grand_total
		outstanding_amount = doc.outstanding_amount
	elif dt in ("Expense Claim"):
		grand_total = doc.total_sanctioned_amount + doc.total_taxes_and_charges
		outstanding_amount = doc.grand_total \
			- doc.total_amount_reimbursed
	elif dt == "Employee Advance":
		grand_total = doc.advance_amount
		outstanding_amount = flt(doc.advance_amount) - flt(doc.paid_amount)
	elif dt == "Fees":
		grand_total = doc.grand_total
		outstanding_amount = doc.outstanding_amount
	else:
		if party_account_currency == doc.company_currency:
			grand_total = flt(doc.get("base_rounded_total") or doc.base_grand_total)
		else:
			grand_total = flt(doc.get("rounded_total") or doc.grand_total)
		outstanding_amount = grand_total - flt(doc.advance_paid)

	# bank or cash
	bank = get_default_bank_cash_account(doc.company, "Bank", mode_of_payment=doc.get("mode_of_payment"),
		account=bank_account)

	if not bank:
		bank = get_default_bank_cash_account(doc.company, "Cash", mode_of_payment=doc.get("mode_of_payment"),
			account=bank_account)

	paid_amount = received_amount = 0
	if party_account_currency == bank.account_currency:
		paid_amount = received_amount = abs(outstanding_amount)
	elif payment_type == "Receive":
		paid_amount = abs(outstanding_amount)
		if bank_amount:
			received_amount = bank_amount
		else:
			received_amount = paid_amount * doc.conversion_rate
	else:
		received_amount = abs(outstanding_amount)
		if bank_amount:
			paid_amount = bank_amount
		else:
			# if party account currency and bank currency is different then populate paid amount as well
			paid_amount = received_amount / doc.conversion_rate
			exchange_rate = doc.conversion_rate

	pe = frappe.new_doc("Payment Entry")
	pe.payment_type = payment_type
	pe.company = doc.company
	pe.cost_center = doc.get("cost_center")
	pe.posting_date = nowdate()
	pe.mode_of_payment = doc.get("mode_of_payment")
	pe.party_type = party_type
	pe.party = doc.get(scrub(party_type))
	pe.contact_person = doc.get("contact_person")
	pe.contact_email = doc.get("contact_email")
	pe.ensure_supplier_is_not_blocked()

	pe.paid_from = party_account if payment_type=="Receive" else bank.account
	pe.paid_to = party_account if payment_type=="Pay" else bank.account
	pe.paid_from_account_currency = party_account_currency \
		if payment_type=="Receive" else bank.account_currency
	pe.paid_to_account_currency = party_account_currency if payment_type=="Pay" else bank.account_currency
	pe.paid_amount = paid_amount
	pe.received_amount = received_amount
	pe.letter_head = doc.get("letter_head")
	
	if payment_type=='Pay' and exchange_rate != 0:
		pe.source_exchange_rate = exchange_rate 

	if pe.party_type in ["Customer", "Supplier"]:
		bank_account = get_party_bank_account(pe.party_type, pe.party)
		pe.set("bank_account", bank_account)
		pe.set_bank_account_data()

	# only Purchase Invoice can be blocked individually
	if doc.doctype == "Purchase Invoice" and doc.invoice_is_blocked():
		frappe.msgprint(_('{0} is on hold till {1}'.format(doc.name, doc.release_date)))
	else:
		if (doc.doctype in ('Sales Invoice', 'Purchase Invoice')
			and frappe.get_value('Payment Terms Template',
			{'name': doc.payment_terms_template}, 'allocate_payment_based_on_payment_terms')):

			for reference in get_reference_as_per_payment_terms(doc.payment_schedule, dt, dn, doc, grand_total, outstanding_amount):
				pe.append('references', reference)
		else:
			pe.append("references", {
				'reference_doctype': dt,
				'reference_name': dn,
				"bill_no": doc.get("bill_no"),
				"due_date": doc.get("due_date"),
				'total_amount': grand_total,
				'outstanding_amount': outstanding_amount,
				'allocated_amount': outstanding_amount
			})

	pe.setup_party_account_field()
	pe.set_missing_values()
	if party_account and bank:
		pe.set_exchange_rate()
		pe.set_amounts()
	return pe

def on_submit(doc, method):
	references = doc.references
	if not doc.reference_no:
		usaepay_transaction_key = ""
		for ref in references:
			# check if the reference is a Sales Invoice and if it can be refunded
			if ref.reference_doctype == "Sales Invoice":
				continue_loop, sales_order, sales_invoice = check_if_payment_can_be_refunded(doc, ref)
				if not continue_loop:
					continue
				
				usaepay_transaction_key = frappe.db.get_value("Sales Order", sales_order, "neb_usaepay_transaction_key")
				if not usaepay_transaction_key:
					continue
	
				response, log = refund_payment(sales_order, doc.remarks, doc.paid_amount)
				if response:
					# update usaepay log and set the reference_no in the Payment Entry
					frappe.db.set_value("Payment Entry", doc.name, "reference_no", response["key"])
					frappe.db.set_value("USAePay Log", log, "payment_entry", doc.name)
					frappe.db.set_value("USAePay Log", log, "sales_return", sales_invoice.name)
					frappe.db.commit()

			elif ref.reference_doctype == "Sales Order":
				sales_order = ref.reference_name

			# check if the reference is a Sales Order and if it can be adjusted
			if sales_order and doc.payment_type == "Receive":
				can_be_adjusted, advance_paid = check_if_payment_can_be_adjusted(doc, sales_order)
				if not usaepay_transaction_key:
					usaepay_transaction_key = frappe.db.get_value("Sales Order", sales_order, "neb_usaepay_transaction_key")

				if can_be_adjusted:
					adjust_response, log = adjust_payment(sales_order, advance_paid)
					
					if adjust_response:
						# set the USAePay Log in the Payment Entry
						frappe.db.set_value("USAePay Log", log, "payment_entry", doc.name, update_modified=False)

						# set the new reference_no in the Payment Entry
						if "key" in adjust_response:
							frappe.db.set_value("Payment Entry", doc.name, "reference_no", adjust_response["key"], update_modified=False)
							frappe.db.commit()

						frappe.msgprint(f"Payment adjusted successfully. New amount is <b>{adjust_response['auth_amount']}</b> for <b>{sales_order}</b>")
				else:
					if not usaepay_transaction_key:
						frappe.db.set_value("Payment Entry", doc.name, "reference_no", usaepay_transaction_key, update_modified=False)

# check if the current user is allowed to process a refund and adjust a payment
def before_submit(doc, method):
	usaepay_roles = get_usaepay_roles()
	references = doc.references

	if not doc.reference_no:
		for ref in references:
			if ref.reference_doctype == "Sales Invoice":
				can_be_refunded, sales_order, sales_invoice = check_if_payment_can_be_refunded(doc, ref)
				if not can_be_refunded:
					continue
					
			elif ref.reference_doctype == "Sales Order":
				sales_order = ref.reference_name

			if sales_order and doc.payment_type == "Receive":
				check_if_payment_can_be_adjusted(doc, sales_order)

def check_if_payment_can_be_adjusted(doc, sales_order):
	so_fields = frappe.db.get_value("Sales Order", sales_order, ["neb_usaepay_transaction_key", "grand_total", "advance_paid"], as_dict=True)
	user_roles = frappe.get_roles()
	usaepay_roles = get_usaepay_roles()

	if so_fields:
		transaction_key = so_fields["neb_usaepay_transaction_key"]
		if transaction_key:
			advance_paid = so_fields["advance_paid"]

			transaction = get_usaepay_transaction_detail(transaction_key, sales_order)
			if not any(role in usaepay_roles["adjust"] for role in user_roles):
				frappe.throw(_("You do not have permission to process an adjustment. Please contact your System Administrator."))

			if flt(advance_paid) > flt(transaction["amount"]):
				return True, advance_paid
		
	return False, 0

def check_if_payment_can_be_refunded(doc, ref):
	user_roles = frappe.get_roles()
	usaepay_roles = get_usaepay_roles()

	# check if one of the user roles is in the usaepay_roles list for refund
	if not any(role in usaepay_roles["refund"] for role in user_roles):
		frappe.throw(_("You do not have permission to process a refund. Please contact your System Administrator."))

	# check if there is a refund for this sales invoice
	refund_transaction_key = frappe.db.get_value("USAePay Log", {"sales_return": ref.reference_name, "action": "Refund"}, ["refund_transaction_key"])

	if refund_transaction_key:
		frappe.msgprint(_("Refund already processed for this Sales Invoice. Transaction Key: {0}").format(refund_transaction_key))
		return False, "", ""

	sales_invoice = frappe.get_doc("Sales Invoice", ref.reference_name)
	sales_order = ""
	for item in sales_invoice.items:
		if item.sales_order:
			sales_order = item.sales_order
			break
	
	if sales_invoice.is_return and sales_order and doc.payment_type == "Pay":
		return True, sales_order, sales_invoice
	
	return False, "", ""

@frappe.whitelist()
def void_payment(name):
	pe = frappe.get_doc("Payment Entry", name)
	usaepay_roles = get_usaepay_roles()
	user_roles = frappe.get_roles()

	if not any(role in usaepay_roles["cancel_payment"] for role in user_roles):
		frappe.throw(_("You do not have permission to void a payment. Please contact System Administrator."))

	if pe.reference_no:
		response, log = void_payment_in_usaepay("Payment Entry", name, pe.reference_no)
		if response:
			if response.get("error"):
				frappe.throw(response["error"])
			elif response.get("result") == "Approved":
				frappe.db.set_value("Payment Entry", name, "reference_no", "")
				frappe.db.set_value("USAePay Log", log, "payment_entry", name)
				frappe.db.commit()
				frappe.msgprint(_("Payment voided successfully."))
	else:
		frappe.throw(_("No reference number found for this Payment Entry."))

@frappe.whitelist()
def get_mode_of_payment(reference_doctype, reference_name):
	if reference_doctype != "Sales Order":
		frappe.response["mode_of_payment"] = "Cash"
		frappe.response["reference_no"] = ""
		
	reference = frappe.db.get_value(reference_doctype, reference_name, "neb_usaepay_transaction_key")
	if reference:
		frappe.response["mode_of_payment"] = "Credit Card"
		frappe.response["reference_no"] = reference
	else:
		frappe.response["mode_of_payment"] = "Cash"
		frappe.response["reference_no"] = ""
