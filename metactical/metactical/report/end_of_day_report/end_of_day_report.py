# Copyright (c) 2022, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
from datetime import date, datetime
from frappe.email.doctype.auto_email_report.auto_email_report import send_now
import pytz
from pytz import timezone

def execute(filters=None):
	columns, data = [], []
	today = None
	if filters.get('date') is not None:
		today = filters.get('date')
	else:
		today = date.today().strftime('%Y-%m-%d')
	columns = get_columns()
	data = get_data(today)
	return columns, data

def get_data(today):
	#today = date.today().strftime('%Y-%m-%d')
	#today = '2022-09-17'
	raw_data = frappe.db.sql("""
								SELECT
									invoice.pos_profile,
									pos.mode_of_payment AS mode_of_payment,
									SUM(pos.amount) AS sys_amount
								FROM
									`tabSales Invoice` as invoice
								LEFT JOIN
									`tabSales Invoice Payment` AS pos ON pos.parent = invoice.name
								WHERE
									invoice.posting_date = %(posting_date)s AND invoice.status = 'Paid'
									AND invoice.is_pos = 1
								GROUP BY
									invoice.pos_profile, mode_of_payment""", {'posting_date': today}, as_dict=1)
	data_pe = frappe.db.sql("""
								SELECT
									'WHS' AS pos_profile,
									pe.mode_of_payment AS mode_of_payment,
									SUM(payment.allocated_amount) AS sys_amount
								FROM
									`tabPayment Entry Reference` AS payment
								LEFT JOIN
									`tabSales Invoice` as invoice ON payment.reference_name = invoice.name
								LEFT JOIN
									`tabPayment Entry` AS pe ON payment.parent = pe.name
								WHERE
									pe.posting_date = %(posting_date)s AND invoice.status = 'Paid' AND invoice.is_pos = 0
								GROUP BY
									mode_of_payment""", {'posting_date': today}, as_dict=1)
	raw_data.extend(data_pe)
	'''data_pos = frappe.db.sql("""
								SELECT
									invoice.pos_profile,
									pos.mode_of_payment AS pos_mode_of_payment,
									pe.mode_of_payment AS pe_mode_of_payment,
									IFNULL(SUM(pos.amount), 0) AS pos_sys_amount,
									IFNULL(SUM(payment.allocated_amount), 0) AS invoice_sys_amount
								FROM
									`tabSales Invoice` as invoice
								LEFT JOIN
									`tabSales Invoice Item` AS item ON item.parent = invoice.name
								LEFT JOIN
									`tabSales Invoice Payment` AS pos ON pos.parent = invoice.name
								LEFT JOIN
									`tabPayment Entry Reference` AS payment ON payment.reference_doctype = 'Sales Invoice'
										AND payment.reference_name = invoice.name
								LEFT JOIN
									`tabPayment Entry` AS pe ON payment.parent = pe.name
								WHERE
									invoice.status = 'Paid' AND 
									(invoice.posting_date = %(posting_date)s OR pe.posting_date = %(posting_date)s)
								GROUP BY
									invoice.pos_profile, mode_of_payment""", {'posting_date': today}, as_dict=1)'''
	profiles = {
		'Downtown Operators': 'DTN', 
		'Edmonds Operators': 'EDM', 
		'Victoria Operators': 'VIC', 
		'Queen Operators': 'QEN',
		'Montreal Operators': 'MON',
		'Gorilla Operators': 'GOR'}
	mop = {
		'Visa': 'Vis',
		'Master Card': 'MC',
		'Amex': 'Amx',
		'Debit Card': 'DC'
	}
	for row in raw_data:
		if row.pos_profile is None or row.pos_profile == 'WHS' or profiles.get(row.pos_profile) is None:
			row.local = 'WHS'
		else:
			row.local = profiles.get(row.pos_profile)
			 
		if row.mode_of_payment is None or mop.get(row.mode_of_payment) is None:
			row.mode = 'Other'
		else:
			row.mode = mop.get(row.mode_of_payment)
		
	#Order the data
	data = []
	for key, value in profiles.items():
		profile_row = []
		ttl = 0
		cash = 0
		for mkey, mode in mop.items():
			mode_row = {"local": value, "mode": mode}
			for row in raw_data:
				if row.local == value and row.mode == mode:
					mode_row['sys_amount'] = mode_row.get('sys_amount', 0) + row.sys_amount
					ttl += row.sys_amount
			profile_row.append(mode_row)
		
		#Add totals row
		profile_row.append({"local": value, "mode": 'TTL', "sys_amount": ttl})
		#Add cash row
		cash_row = {"local": value, "mode": "CSH"}
		for row in raw_data:
			if row.local == value and row.mode_of_payment == 'Cash':
				cash_row["sys_amount"] = cash_row.get('sys_amount', 0) + row.sys_amount
				cash += row.sys_amount
		profile_row.append(cash_row)
		
		#Add AITTL
		profile_row.append({"local": value, "mode": "AITTL", "sys_amount": ttl + cash})
		profile_row.append({})
		profile_row[0].update({
			'gttl_label': 'SYS',
			'gttl': ttl + cash
		})
		profile_row[1].update({'gttl_label': 'ACTL'})
		data.extend(profile_row)
		
	#Add WHS data
	ttl = 0
	cash = 0
	whs_row = []
	for mkey, mode in mop.items():
		mode_row = {"local": 'WHS', "mode": mode}
		for row in raw_data:
			if row.local == 'WHS' and row.mode == mode:
				mode_row['sys_amount'] = mode_row.get('sys_amount', 0) + row.sys_amount
				ttl += row.sys_amount
		whs_row.append(mode_row)
	#Add totals row
	whs_row.append({"local": 'WHS', "mode": 'TTL', "sys_amount": ttl})
	#Add cash row
	cash_row = {"local": 'WHS', "mode": "CSH"}
	for row in raw_data:
		if row.local == 'WHS' and row.mode_of_payment == 'Cash':
			cash_row["sys_amount"] = cash_row.get('sys_amount', 0) + row.sys_amount
			cash += row.sys_amount
	whs_row.append(cash_row)
	whs_row.append({"local": 'WHS', "mode": "AITTL", "sys_amount": ttl + cash})
	whs_row[0].update({
		'gttl_label': 'SYS',
		'gttl': ttl + cash
	})
	whs_row[1].update({'gttl_label': 'ACTL'})
	data.extend(whs_row)		
	return data
	
def get_columns():
	columns = [
		{
			"fieldtype": "Data",
			"fieldname": "local",
			"label": "Local",
			"width": 100
		},
		{
			"fieldtype": "Data",
			"fieldname": "mode",
			"label": "Mode",
			"width": 100,
			"precision": 2
		},
		{
			"fieldtype": "Currency",
			"fieldname": "sys_amount",
			"label": "Sys",
			"width": 150,
			"precision": 2
		},
		{
			"fieldtype": "Currency",
			"fieldname": "actl",
			"label": "ACTL",
			"width": 150,
			"precision": 2
		},
		{
			"fieldtype": "Currency",
			"fieldname": "diff",
			"label": "DIFF",
			"width": 150,
			"precision": 2
		},
		{
			"fieldtype": "Data",
			"fieldname": "hidden",
			"width": 100,
		},
		{
			"fieldtype": "Data",
			"fieldname": "gttl_label",
			"label": "GTTL",
			"width": 150
		},
		{
			"fieldtype": "Currency",
			"fieldname": "gttl",
			"width": 150,
			"precision": 2
		}
	]
	return columns

def send_report():
	vancouver = timezone('America/Vancouver')
	#return datetime.now().strftime("%H:%M")
	return datetime.utcnow().astimezone(vancouver).strftime("%H:%M")
	"""exists = frappe.db.exists('Auto Email Report', 'End of Day Report')
	if exists:
		send_now("End of Day Report")"""
