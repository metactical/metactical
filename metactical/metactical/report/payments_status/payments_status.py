# Copyright (c) 2013, Techlift Technologies and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe

def execute(filters=None):
	columns, data = [], []
	columns = [
		{
			"fieldname": "so_date",
			"label": "Date",
			"fieldtype": 'Date',
			'width': 100
		},
		{
			"fieldname": "sales_order",
			"label": "Sales order #",
			"fieldtype": 'Link',
			'options': 'Sales Order',
			'width': 100
		},
		{
			"fieldname": "customer",
			"label": "Customer Name",
			"fieldtype": 'Link',
			"options": "Customer",
			'width': 150
		},	
		{
			"fieldname": "grand_total",
			"label": "Grand Total",
			"fieldtype": 'Currency',
			'width': 150
		},
		{
			"fieldname": "advance_paid",
			"label": "Advance Paid",
			"fieldtype": 'Currency',
			'width': 150
		},
		{
			"fieldname": "balance_due",
			"label": "Balance Due",
			"fieldtype": 'Currency',
			'width': 150
		},
		{
			"fieldname": "credit_due",
			"label": "Credit Due",
			"fieldtype": 'Currency',
			'width': 150
		},
		{
			"fieldname": "notes",
			"label": "Notes",
			"fieldtype": 'Data',
			'width': 150
		}
	]
	
	where_filter = {"from_date": filters.from_date, "to_date": filters.to_date}
	
	initial = frappe.db.sql('''SELECT
								so.transaction_date AS so_date,
								so.name AS sales_order,
								so.customer,
								so.grand_total,
								so.advance_paid,
								so.ais_payment_notes AS notes
							FROM
								`tabSales Order` AS so
							WHERE
								so.transaction_date BETWEEN %(from_date)s AND %(to_date)s
								AND so.docstatus = 1
						''', where_filter, as_dict=1)
	for sales_order in initial:
		if not sales_order['notes']:
			sales_order.update({"notes": '<button class="btn btn-xs btn-default" onClick="add_notes(\'' + sales_order['sales_order'] + '\')">Add Notes</button>'})
	data = get_balance(initial)
	data = get_credit(data)
	
	return columns, data
	
def get_balance(data):
	if data:
		for row in data:
			c_or_b = row.grand_total - row.advance_paid
			if c_or_b > 0:
				row.update({
					"balance_due": c_or_b
				})
			else:
				row.update({
					"balance_due": 0
				})
	return data
	
def get_credit(data):
	if data:
		accounts = frappe.db.get_list("Account", filters={'account_type': 'Receivable'})
		account_list = "("
		no = 0
		if accounts:
			for account in accounts:
				if no > 0:
					account_list += ", "
				account_list += "'" + account.name + "'"
				no = no + 1
		account_list += ")"
		
			
		
		for row in data:
			credit_due = 0.0
			#For extra unassigned payment
			query = frappe.db.sql('''
				SELECT
					SUM(credit_in_account_currency) AS credit_due
				FROM
					`tabGL Entry`
				WHERE
					account IN {} AND party = %(party)s
					AND party_type = 'Customer' AND against_voucher IS NULL
			'''.format(account_list), {"party": row.customer}, as_dict=1)
			
			if query[0] and query[0].credit_due is not None:
				credit_due = query[0].credit_due
		
			#For extra advance paid then Sales Order amended to reduce amount due
			c_or_b = row.grand_total - row.advance_paid
			if c_or_b < 0:
				credit_due = credit_due + (c_or_b * -1)
			
			row.update({"credit_due": credit_due})		
	return data
	
@frappe.whitelist()
def insert_notes(**args):
	args = frappe._dict(args)
	doc = frappe.get_doc('Sales Order', args.sales_order)
	doc.db_set("ais_payment_notes", args.notes, notify=True)
	return "Success"
