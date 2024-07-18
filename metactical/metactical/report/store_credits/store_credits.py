# Copyright (c) 2024, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
from metactical.custom_scripts.utils.metactical_utils import (
		get_customer_email_and_phone, 
		search_customer_by_phone_email
	)

def execute(filters=None):
	fetch_all = filters.get('fetch_all') if filters.get('fetch_all') else 0
	phone = filters.get('phone') if filters.get('phone') else ''
	email = filters.get('email') if filters.get('email') else ''
	sales_invoice = filters.get("sales_invoice") if filters.get("sales_invoice") else ""

	customers_list = []
	customer = filters.get('customer') if filters.get('customer') else ''
	if customer:
		customers_list.append(customer)

	if not customer and not fetch_all and not phone and not email and not sales_invoice:
		frappe.throw("Please select a customer")

	if phone or email:
		customers = search_customer_by_phone_email(phone, email)
		if customers:
			customers_list += customers

	columns = get_columns(sales_invoice)
	data = get_data(customers_list, sales_invoice)

	return columns, data

def get_data(customers, sales_invoice):
	data = []
	
	customer_filter = ""
	if len(customers) > 0:
		customers = ", ".join([f"'{customer}'" for customer in customers])
		customer_filter = f"AND party IN ({customers})"

	sales_invoice_filter = ""
	if sales_invoice:
		sales_invoice_filter = f"AND voucher_no = '{sales_invoice}'"
		
	total_unpaid = frappe._dict(
		frappe.db.sql(
			f"""
				select party, sum(debit_in_account_currency) - sum(credit_in_account_currency) as amount
				from `tabGL Entry`
				where party_type = 'Customer' and is_cancelled = 0 
				{customer_filter}
				{sales_invoice_filter}
				group by party""",
		)
	)

	for customer, amount in total_unpaid.items():
		sales_invoices = frappe.db.get_list("Sales Invoice", filters={"customer": customer, "status": ["in", ["Overdue", "Unpaid", "Partly Paid"]]}, fields=["name", "outstanding_amount"])
		if sales_invoices:
			amount = amount - sum([d.get('outstanding_amount') for d in sales_invoices])

		# if the filter is to fetch all customers, we will only show customers with credit
		if amount >= -0.01:
			if len(customers) > 0:
				amount = 0
			else: continue

		credit_docs = get_credit_docs(customer, sales_invoice)
		row = {
			"customer": "<a href='/app/customer/{0}' _target='blank'>{0}</a>".format(customer),
			"credit": amount,
			"store_credit_no": credit_docs
		}

		contact = get_customer_email_and_phone(customer)
		if contact:
			row["email"] = contact[0].get('email_id')
			row["mobile"] = contact[0].get('mobile_no') if contact[0].get('mobile_no') else contact[0].get('phone')

		data.append(row)
	
	return data

def get_credit_docs(customer, sales_invoice):
	sales_invoice_filter = ""
	if sales_invoice:
		sales_invoice_filter = f"AND against_voucher = '{sales_invoice}'"

	credits = frappe.db.sql(f"""
		SELECT against_voucher, voucher_type, voucher_no, debit_in_account_currency, credit_in_account_currency
		FROM `tabGL Entry`
		WHERE party = '{customer}'
		{sales_invoice_filter}	
		AND is_cancelled = 0
	""", as_dict=True)

	# group by against_voucher 
	against_voucher_group = {}
	for credit in credits:
		if credit.against_voucher not in against_voucher_group:
			against_voucher_group[credit.against_voucher] = []
		
		against_voucher_group[credit.against_voucher].append(credit)


	# move jounrnal entries without against voucher but voucher_no matches with sales invoice
	docs_without_against_voucher = []
	if None in against_voucher_group:
		for v in against_voucher_group[None]:
			if v.voucher_no in against_voucher_group:
				against_voucher_group[v.voucher_no].append(v)
			else:
				docs_without_against_voucher.append(v)

		if len(docs_without_against_voucher) > 0:
			against_voucher_group["None"] = docs_without_against_voucher 
			# remove the None key
			against_voucher_group.pop(None)


	# filter out unpaid docs from documents in the name of the cusotmer
	unpaid_docs = []
	for invoice, vouchers in against_voucher_group.items():
		if invoice == "None": # gl entries without against voucher (not attached to a sales invoice)
			for voucher in vouchers:
				if voucher.credit_in_account_currency > 0:
					# if voucher.voucher_type == "Journal Entry":
						# accounts = frappe.get_doc("Journal Entry", voucher.voucher_no).accounts
						# for account in accounts:
						# 	if account.debit_in_account_currency > 0 and account.reference_type == "Sales Invoice":
						# 		return_si = frappe.db.get_value("Sales Invoice", 
						# 											{
						# 												"return_against": account.reference_name, 
						# 												"neb_store_credit_beneficiary": customer,
						# 												"grand_total": -1 * account.debit_in_account_currency
						# 											}, "name")

						# 		if return_si:
						# 			voucher.voucher_no = return_si
						# 			voucher.voucher_type = "Sales Invoice"
						# 			unpaid_docs.append(voucher)
					# else:
					unpaid_docs.append(voucher)
		else:
			sum_credit = sum([voucher.credit_in_account_currency for voucher in vouchers])
			sum_debit = sum([voucher.debit_in_account_currency for voucher in vouchers])

			if sum_credit == sum_debit:
				continue

			elif sum_credit > sum_debit:
				for voucher in vouchers:
					if voucher.credit_in_account_currency > 0 and len(vouchers) == 2: # the amount paid is greater than invoice amount
						unpaid_docs.append(voucher)
								
					elif voucher.credit_in_account_currency > 0 and len(vouchers) == 1: # store credit given by a journal entry
						unpaid_docs.append(voucher)		

					elif voucher.credit_in_account_currency > 0 and len(vouchers) > 2: # for return documents and journal entries
						if voucher.voucher_type in ["Sales Invoice"] and voucher.voucher_no != invoice:
							unpaid_docs.append(voucher)
						elif voucher.voucher_type in ["Journal Entry"]:
							unpaid_docs.append(voucher)
						elif voucher.voucher_type in ["Payment Entry"]:
							sum_of_payment_entries = sum([voucher.credit_in_account_currency for voucher in vouchers if voucher.voucher_type == "Payment Entry" and voucher.credit_in_account_currency > 0])
							if sum_of_payment_entries == vouchers[0].debit_in_account_currency:
								continue
							elif vouchers[0].debit_in_account_currency == voucher.credit_in_account_currency:
								continue
							else:
								unpaid_docs.append(voucher)


	docs = ""
	if sales_invoice:
		docs = f"<a href='/app/sales-invoice/{sales_invoice}' _target='blank'>{sales_invoice}</a>"
	else:
		for ud in unpaid_docs:
			if ud.voucher_type == "Sales Invoice":
				docs += f"<a href='/app/sales-invoice/{ud.voucher_no}' _target='blank'>{ud.voucher_no}</a>, "
			elif ud.voucher_type == "Journal Entry":
				docs += f"<a href='/app/journal-entry/{ud.voucher_no}' _target='blank'>{ud.voucher_no}</a>, "
			elif ud.voucher_type == "Payment Entry":
				docs += f"<a href='/app/payment-entry/{ud.voucher_no}' _target='blank'>{ud.voucher_no}</a>, "
			elif ud.voucher_type == "Sales Order":
				docs += f"<a href='/app/sales-order/{ud.voucher_no}' _target='blank'>{ud.voucher_no}</a>, "

		if docs.endswith(", "):
			docs = docs[:-2]

	return docs

def get_columns(sales_invoice=False):
	columns = [
		{
			"label": "Customer",
			"fieldname": "customer",
			"fieldtype": "Data",
			"width": 150
		},
		{
			"label": "Email",
			"fieldname": "email",
			"fieldtype": "Data",
			"width": 150
		},
		{
			"label": "Mobile",
			"fieldname": "mobile",
			"fieldtype": "Data",
			"width": 150
		},
		{
			"label": "Credit",
			"fieldname": "credit",
			"fieldtype": "Currency",
			"width": 150
		},
		{
			"label": "Store credit no",
			"fieldname": "store_credit_no",
			"fieldtype": "Data",
			"width": 150
		}
	]

	return columns
