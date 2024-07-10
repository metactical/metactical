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

	customers_list = []
	customer = filters.get('customer') if filters.get('customer') else ''
	if customer:
		customers_list.append(customer)

	if not customer and not fetch_all and not phone and not email:
		frappe.throw("Please select a customer")

	if phone or email:
		customers = search_customer_by_phone_email(phone, email)
		if customers:
			customers_list += customers

	columns = get_columns()
	data = get_data(customers_list) 

	return columns, data

def get_data(customers):
	data = []
	
	customer_filter = ""
	if len(customers) > 0:
		customers = ", ".join([f"'{customer}'" for customer in customers])
		customer_filter = f"AND party IN ({customers})"

	
	# store_credits = frappe.db.sql(f"""
	# 				SELECT * from `tabJournal Entry Account`
	# 				WHERE account = '{store_credit_account}'
	# 				{customer_filter}
	# 				ORDER BY creation DESC
	# 				""", as_dict=True)

	total_unpaid = frappe._dict(
		frappe.db.sql(
			f"""
		select party, sum(debit_in_account_currency) - sum(credit_in_account_currency) as amount
		from `tabGL Entry`
		where party_type = 'Customer' and is_cancelled = 0 
		 {customer_filter}
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

		row = {
			"customer": "<a href='/app/customer/{0}' _target='blank'>{0}</a>".format(customer),
			"credit": amount
		}

		contact = get_customer_email_and_phone(customer)
		if contact:
			row["email"] = contact[0].get('email_id')
			row["mobile"] = contact[0].get('mobile_no') if contact[0].get('mobile_no') else contact[0].get('phone')

		data.append(row)
	
	return data

def get_columns():
	return [
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
		}
	]
