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
		
	years_before = frappe.utils.add_years(frappe.utils.nowdate(), -4)
	total_unpaid = frappe._dict(
		frappe.db.sql(
			f"""
				select party, sum(debit_in_account_currency) - sum(credit_in_account_currency) as amount
				from `tabGL Entry`
				where party_type = 'Customer' and is_cancelled = 0 and posting_date >= '{years_before}'
				{customer_filter}
				{sales_invoice_filter}
				group by party""",
		)
	)

	pos_customers = frappe.db.get_list("Customer", )
	
	for customer, amount in total_unpaid.items():
		sales_invoices = frappe.db.get_list("Sales Invoice", filters={"customer": customer, "status": ["in", ["Overdue", "Unpaid", "Partly Paid"]]}, fields=["name", "outstanding_amount"])
		if sales_invoices:
			amount = amount - sum([d.get('outstanding_amount') for d in sales_invoices])

		# if the filter is to fetch all customers, we will only show customers with credit
		if amount >= -0.02:
			if len(customers) > 0:
				amount = 0
			else: continue
		
		if customer.startswith("DefaultPOS"):
			data.append({
				"customer": customer,
				"credit": amount,
				"original_credit": 0,
				"store_credit_no": "POS",
				"invoice": ""
			})

			continue
		
		if sales_invoice:
			rows = get_credit_info_for_si(customer, sales_invoice)
		else:
			rows = get_credit_docs(customer, sales_invoice)

		contact = get_customer_email_and_phone(customer)
		
		if contact:
			for row in rows:
				if sales_invoice and sales_invoice != row.get('invoice'):
					continue

				row["email"] = contact[0].get('email_id')
				row["mobile"] = contact[0].get('mobile_no') if contact[0].get('mobile_no') else contact[0].get('phone')

				data.append(row)
	
	return data

def get_credit_info_for_si(customer, sales_invoice):
	si = frappe.db.get_values("Sales Invoice", sales_invoice, ["customer", "neb_store_credit_beneficiary", "return_against"], as_dict=True)
	if not si:
		return []

	beneficiary = si[0].get('neb_store_credit_beneficiary')
	if beneficiary and beneficiary != customer:
		total_credit_used = get_si_credit_docs(beneficiary, si)
		original_credit = frappe.db.get_value("Sales Invoice", sales_invoice, "grand_total")

		return [{
			"customer": beneficiary,
			"customer_name": frappe.db.get_value("Customer", beneficiary, "customer_name"),
			"credit": original_credit + total_credit_used,
			"original_credit": original_credit,
			"store_credit_no": f"<a href='/app/sales-invoice/{sales_invoice}'>{sales_invoice}</a>",
			"invoice": sales_invoice
		}]

	else:
		credit_docs = get_credit_docs(customer, si[0].return_against)
		return credit_docs

def get_si_credit_docs(customer, sales_invoice):
	sales_invoice = sales_invoice[0]

	gl_entries = frappe.db.get_list("GL Entry", filters={"against_voucher": sales_invoice.return_against, "is_cancelled": 0, "voucher_type": "Journal Entry"}, fields=["voucher_no", "debit_in_account_currency", "credit_in_account_currency", "party"])
	if not gl_entries:
		return []

	credit_docs = []
	je_entry_names = [ge.get('voucher_no') for ge in gl_entries]
	je_account_entires = frappe.db.get_list("Journal Entry Account", filters={"parent": ["in", je_entry_names], "party": customer}, fields=["parent", "reference_name", "debit_in_account_currency", "credit_in_account_currency"])
	
	used_credits = 0
	for je in je_account_entires:
		if je.get('reference_name') and je.get("credit_in_account_currency") > 0:
			used_credits += je.get("credit_in_account_currency")

	return used_credits

def get_credit_docs(customer, sales_invoice):
	years_before = frappe.utils.add_years(frappe.utils.nowdate(), -4)
	sales_invoice_filter = ""

	if sales_invoice:
		sales_invoice_filter = f"AND against_voucher = '{sales_invoice}'"

	credits = frappe.db.sql(
		f"""
		SELECT against_voucher, voucher_type, voucher_no, debit_in_account_currency, credit_in_account_currency
		FROM `tabGL Entry`
		WHERE party = '{customer}'
		{sales_invoice_filter}
		AND is_cancelled = 0 and posting_date >= '{years_before}'
		""", as_dict=True)

	updated_credits = []
	credits_copy = credits.copy()
	for credit in credits:
		if credit.voucher_type == "Sales Invoice":
			if credit.voucher_no == credit.against_voucher:
				updated_credits = check_and_remove_match(credit, credits_copy, same_voucher=True)
			elif credit.voucher_no != credit.against_voucher:
				updated_credits = check_and_remove_match(credit, credits_copy, same_voucher=False)
		elif credit.voucher_type == "Journal Entry":
			updated_credits = check_and_remove_match(credit, credits_copy, same_voucher=False)

	rows = []

	for credit in updated_credits:
		if credit.credit_in_account_currency == 0:
			updated_credits.remove(credit)

	for credit in updated_credits:
		if credit.voucher_type == "Sales Invoice":
			original_credit = frappe.db.get_values("Sales Invoice", credit.voucher_no, ["grand_total", "status", "customer_name", "neb_store_credit_beneficiary"], as_dict=True)
			remaining_credit = get_remaining_credit(credit, customer)

			if len(original_credit) == 0:
				continue
			elif original_credit[0].get('status') != "Return":
				continue
			elif frappe.db.get_value("Sales Invoice", credit.voucher_no, "is_pos"):
				continue
			
			duplicate = False
			for row in rows:
				if row.get('invoice') == credit.voucher_no:
					duplicate = True

			if not duplicate and remaining_credit > 0:
				beneficiary = original_credit[0].get('neb_store_credit_beneficiary') if original_credit[0].get('neb_store_credit_beneficiary') else original_credit[0].get('customer_name')
				rows.append({
					"customer": customer,
					"credit": -1 * remaining_credit,
					"customer_name": beneficiary,
					"original_credit": original_credit[0].get('grand_total'),
					"store_credit_no": "<a href='/app/sales-invoice/" + credit.voucher_no + "'>" + credit.voucher_no + "</a>",
					"invoice": credit.voucher_no
				})

		elif credit.voucher_type == "Journal Entry":
			if not credit.return_doc:
				gl_entries = frappe.db.get_values("GL Entry", {"voucher_no": credit.voucher_no, "debit_in_account_currency": [">", "0"]}, ["against_voucher"], as_dict=True)
				
				if len(gl_entries) == 0:
					continue
				else:
					return_sales_invoices = frappe.db.get_values("Sales Invoice", {"return_against": gl_entries[0].get('against_voucher'), "is_return": 1, "docstatus": 1, "is_pos": 0}, ["name", "grand_total", "neb_store_credit_beneficiary", "status"], as_dict=True)
					original_credit_amount = frappe.db.get_value("Journal Entry Account", {"parent": credit.voucher_no, "reference_type": "Sales Invoice", "reference_name": gl_entries[0].get('against_voucher')}, "debit_in_account_currency")

					if len(return_sales_invoices) == 0:
						continue

					for rs in return_sales_invoices:
						if rs.get('status') != "Return":
							continue

						if rs.get('neb_store_credit_beneficiary') and rs.get('neb_store_credit_beneficiary') != customer:
							continue
						
						if -1 * rs.get('grand_total') == original_credit_amount:
							credit.return_doc = rs.get('name')
							break
			

			original_credit = frappe.db.get_values("Sales Invoice", credit.return_doc, ["grand_total", "status", "neb_store_credit_beneficiary", "name", "customer_name"], as_dict=True)
			remaining_credit = get_remaining_credit(credit, customer)
			
			if len(original_credit) == 0:
				continue
			elif original_credit[0].get('status') != "Return":
				continue

			if original_credit[0].get('neb_store_credit_beneficiary') != customer:
				continue
			
			duplicate = False
			for row in rows:
				if row.get('invoice') == credit.return_doc:
					duplicate = True
					continue
			
			if duplicate or remaining_credit <= 0:
				continue

			beneficiary = original_credit[0].get('neb_store_credit_beneficiary') if original_credit[0].get('neb_store_credit_beneficiary') else original_credit[0].get('customer_name')
			rows.append({
				"customer": customer,
				"credit": -1 * remaining_credit,
				"customer_name": beneficiary,
				"original_credit": original_credit[0].get('grand_total'),
				"store_credit_no": "<a href='/app/sales-invoice/" + credit.return_doc + "'>" + credit.return_doc + "</a>",
				"invoice": credit.return_doc
			})

	return rows

def get_remaining_credit(credit, customer):
	# check in gl entries if there is a credit entry is linked with an invoice
	if credit.voucher_type == "Journal Entry":
		linked_doc = frappe.db.get_list("Journal Entry Account", filters={"parent": credit.voucher_no, "credit_in_account_currency": [">", 0]}, fields=["reference_name", "reference_type", "debit_in_account_currency", "credit_in_account_currency"])
		credit.credit_in_account_currency = 0
		if linked_doc:
			for ld in linked_doc:
				if not ld.get("reference_name"):
					credit.credit_in_account_currency += ld.get("credit_in_account_currency")

	elif credit.voucher_type == "Sales Invoice":
		# check if the credit is used in a payment entry
		used_credits = frappe.db.get_values("GL Entry", {"against_voucher": credit.against_voucher, "party": customer, "voucher_type": "Payment Entry", "debit_in_account_currency": [">", 0]}, ["voucher_no"], as_dict=True)
		if used_credits:
			pes_used_for_credit_transfer = [uc.get('voucher_no') for uc in used_credits]

			# get all the payments made with the credit using the payment entry
			transfered_credits = frappe.db.get_list("GL Entry", {"voucher_no": ["in", pes_used_for_credit_transfer], "credit_in_account_currency": [">", 0], "party": customer, "against_voucher": ["is", "set"]}, ["credit_in_account_currency"])
			total_used = sum([tc.get('credit_in_account_currency') for tc in transfered_credits])
			credit.credit_in_account_currency -= total_used

	return credit.credit_in_account_currency

def check_and_remove_match(credit, credits, same_voucher=False):
	if credit.voucher_type == "Sales Invoice":
		for credit_entry in credits:
			if same_voucher:
				if credit_entry.voucher_type == "Payment Entry" and credit_entry.against_voucher == credit.voucher_no:
					if credit_entry.credit_in_account_currency == credit.debit_in_account_currency:
						credits.remove(credit_entry)
						credits.remove(credit)
						return credits
						
			elif not same_voucher:
				if credit_entry.against_voucher == credit.against_voucher:
					if (credit_entry.debit_in_account_currency == credit.credit_in_account_currency and 
						credit_entry.voucher_type == "Journal Entry"):
						credit_entry.return_doc = credit.voucher_no

						# find credit in credits and delete
						for c in credits:
							if c == credit:
								credits.remove(c)
								break

						return credits
					
					elif credit_entry.voucher_type == "Payment Entry" and credit_entry.debit_in_account_currency == credit.credit_in_account_currency:
						credits.remove(credit_entry)
						credits.remove(credit)
						
						return credits
	elif credit.voucher_type == "Journal Entry":
		if len(credits) == 1:
			if credit.credit_in_account_currency == 0:
				credits.remove(credit)
			return credits

		for credit_entry in credits:
			if (credit_entry.voucher_no == credit.voucher_no and credit_entry.voucher_type == "Journal Entry"):
				if credit_entry.credit_in_account_currency == 0:
					credits.remove(credit_entry)

	return credits

def get_linked_doc_from_payment_entry(voucher):
	payment_entry = frappe.get_doc("Payment Entry", voucher.voucher_no)
	references = payment_entry.references

	if references:
		if len(references) == 1:
			if references[0].reference_doctype == "Sales Invoice":
				voucher.voucher_no = references[0].reference_name
				voucher.voucher_type = "Sales Invoice"

			# elif references[0].reference_doctype == "Sales Order":
			# 	voucher.voucher_no = references[0].reference_name
			# 	voucher.voucher_type = "Sales Order"

	return None
			

def get_columns(sales_invoice=False):
	columns = [
		{
			"label": "Customer",
			"fieldname": "customer",
			"fieldtype": "Data",
			"width": 150
		},
		{
			"label": "Customer Name",
			"fieldname": "customer_name",
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
			"label": "Balance Store Credit Left",
			"fieldname": "credit",
			"fieldtype": "Currency",
			"width": 150
		},
		{
			"label": "Original Store Credit amount",
			"fieldname": "original_credit",
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
