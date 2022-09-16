# Copyright (c) 2022, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
from datetime import date

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

def get_data(date):
	raw_data = frappe.db.sql("""
								SELECT
									invoice.pos_profile,
									CASE
										WHEN pos.mode_of_payment IS NOT NULL THEN pos.mode_of_payment
										WHEN pe.mode_of_payment IS NOT NULL THEN pe.mode_of_payment
									END AS mode_of_payment,
									CASE
										WHEN pos.amount IS NOT NULL THEN SUM(pos.amount)
										WHEN payment.allocated_amount IS NOT NULL THEN SUM(payment.allocated_amount) 
									END AS sys_amount
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
									invoice.status = 'Paid' AND invoice.posting_date = %(posting_date)s
								GROUP BY
									invoice.pos_profile, mode_of_payment""", {'posting_date': date}, as_dict=1)
	profiles = {
		'Downtown Operators': 'DTN', 
		'Edmodns Operators': 'EDM', 
		'Victoria Operators': 'VIC', 
		'Queen Operators': 'QEN',
		'Montreal Operators': 'MON',
		'Gorilla Operators': 'GOR'}
	mop = {
		'VISA': 'Vis',
		'Master Card': 'MC',
		'Amex': 'Amx',
		'Debit Card': 'DC'
	}
	for row in raw_data:
		if row.pos_profile is None or profiles.get(row.pos_profile) is None:
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
					mode_row['sys_amount'] = row.sys_amount
					ttl += row.sys_amount
					break
			profile_row.append(mode_row)
		
		#Add totals row
		profile_row.append({"local": value, "mode": 'TTL', "sys_amount": ttl})
		#Add cash row
		cash_row = {"local": value, "mode": "CSH"}
		for row in raw_data:
			if row.local == value and row.mode_of_payment == 'Cash':
				cash_row["sys_amount"] = row.sys_amount
				cash = row.sys_amount
				break
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
				mode_row['sys_amount'] = row.sys_amount
				ttl += row.sys_amount
		whs_row.append(mode_row)
	#Add totals row
	whs_row.append({"local": 'WHS', "mode": 'TTL', "sys_amount": ttl})
	#Add cash row
	for row in raw_data:
		if row.local == 'WHS' and row.mode_of_payment == 'Cash':
			whs_row.append({"local": 'WHS', "mode": "CSH", "sys_amount": row.sys_amount})
			cash = row.sys_amount
			break
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
