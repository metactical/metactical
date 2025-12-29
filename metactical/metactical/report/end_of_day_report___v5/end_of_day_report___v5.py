# Copyright (c) 2023, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
import requests
from datetime import datetime
from dateutil.relativedelta import relativedelta
from metactical.api.end_of_day_report import get_us_report_data

def execute(filters=None):
	columns, data = [], []
	columns = get_columns(filters)

	filters.end_date = filters.get("date")

	# Get Canada and US data
	data = get_ca_data(filters)

	# # Get USA data
	us_data = get_us_data(filters)
	if len(us_data) > 0:
		data.append({"Location": "USA"})
		data.extend(us_data)
		
	for row in data:
		if row.get("eod_link"):
			row["location"] = row.get("eod_link")
  
	return columns, data
	
def get_columns(filters):
	columns = [
		{
			"fieldname": "location",
			"fieldtype": "Location",
			"label": "Location",
			"options": "Lead Source",
			"width": 200
		},
		{
			"fieldname": "total_without_tax",
			"fieldtype": "Currency",
			"label": "Total Without Tax",
			"width": 140
		},
		{
			"fieldname": "cash_sales",
			"fieldtype": "Currency",
			"label": "Cash Sales",
			"width": 120
		},
		{
			"fieldname": "difference",
			"fieldtype": "Currency",
			"label": "Difference",
			"width": 120,
			"options": "Currency",
		},
		{
			"fieldname": "notes",
			"fieldtype": "Data",
			"label": "Note",
			"width": 120,
			"options": "Currency",
		},
		{
			"fieldname": "space",
			"fieldtype": "Data",
			"label": "",
			"width": 100
		},
		{
			"fieldname": "total_mtd",
			"fieldtype": "Currency",
			"label": "CMA Sales",
			"width": 120
		},
		{
			"fieldname": "total_pmtd",
			"fieldtype": "Currency",
			"label": "PYMA Sales",
			"width": 120
		}
	]
	return columns
	
def get_ca_data(filters):
	data = []
 
	default_company = frappe.db.get_single_value("Global Defaults", "default_company")
	sources = frappe.db.get_list("Lead Source", ['name', 'ais_report_label'], {
									"name": ["not in", ["Website - Valley", "Website - MRK", "Website - Zelen", "Store - Camo - Montreal"]],
									"neb_company": default_company,
								})
 
	total_store_data = get_website_stores_data(filters, "Stores", sources)
	stores_data = total_store_data[0]
	
	# sort the data based on the array given
	stores_order = [ "Store - Camo - Downtown", 
		  		"Store - Camo - Edmonds", 
				"Store - Camo - Victoria",
			 	"Store - Camo - Queen", 
			  	"Store - Gorilla - Vancouver"
			]
 
	order_index = {name: i for i, name in enumerate(stores_order)}
	stores_data = sorted(stores_data, key=lambda x:  order_index.get(x.get("name"), len(stores_order)))
	data.extend(stores_data)

	data.append({"Location": "Online"})
	total_web_data = get_website_stores_data(filters, "Website", sources)
	web_data = total_web_data[0]

	websites_order = ["Website - RAS", "Website - Camo", "Website - Gorilla", "Website - GPD"]
	web_data = sorted(web_data, key=lambda x:  order_index.get(x.get("name"), len(websites_order)))
	data.extend(web_data)
 
	add_totals(data, total_store_data, total_web_data, "CAD")
 	
	return data

def get_us_data(filters):
	data = []
	us_companies = frappe.db.get_list("Company",
		filters={"country": "United States", "is_group": 0},
		fields=["name"]
	)
	
	if not us_companies:
		return []

	companies = [company.name for company in us_companies]
	sources = frappe.db.get_all("Lead Source", {"neb_company": ["in", companies]}, ['name', 'ais_report_label'])
	
	total_store_data = get_website_stores_data(filters, "Stores", sources)
	stores_data = total_store_data[0]
	data.extend(stores_data)

	data.append({"Location": "Online"})
	total_web_data = get_website_stores_data(filters, "Website", sources)
	web_data = total_web_data[0]
	data.extend(web_data)
 
	add_totals(data, total_store_data, total_web_data, "USD")
 	
	return data

def add_totals(data, total_store_data, total_web_data, currency):
	total_stores_with_tax = total_store_data[1]
	total_stores_without_tax = total_store_data[2]
	stores_total_mtd = total_store_data[3]
	stores_total_pmtd = total_store_data[4]
	total_cash_sales = total_store_data[5]
 
	total_web_with_tax = total_web_data[1]
	total_web_without_tax = total_web_data[2]
	web_total_mtd = total_web_data[3]
	web_total_pmtd = total_web_data[4]
	
	#Add an empty row followed with totals rows
	data.append({})
	data.append({
		"location": "Stores - Total", 
		"total_with_tax": total_stores_with_tax, 
		"cash_sales": total_cash_sales,
		"total_without_tax": total_stores_without_tax,
		"total_mtd": stores_total_mtd,
		"total_pmtd": stores_total_pmtd,
	
	})
	data.append({
		"location": "Websites - Total", 
		"total_with_tax": total_web_with_tax, 
		"total_without_tax": total_web_without_tax,
		"total_mtd": web_total_mtd,
		"total_pmtd": web_total_pmtd
	})
	data.append({
		"location": f"{currency} Total",
		"total_with_tax": total_stores_with_tax + total_web_with_tax,
		"total_without_tax": total_stores_without_tax + total_web_without_tax,
		"cash_sales": total_cash_sales,
		"total_mtd": stores_total_mtd + web_total_mtd,
		"total_pmtd": stores_total_pmtd + web_total_pmtd,
	})
	
def get_website_stores_data(filters, location, sources):
	data = []
	total_with_tax = 0
	total_without_tax = 0
	total_mtd = 0
	total_pmtd = 0
	total_cash_sales = 0
	
	date = filters.get("date")
	
	for source in sources:
		matches = False
		doctype = ""
		wtype = source.name.split("-")
		row = {"location": source.ais_report_label, "total_with_tax": 0, "total_without_tax": 0}
  		
		#Check if you're getting website or stores data
		if location == "Website" and len(wtype) > 0 and wtype[0].strip() == "Website" \
			and source.ais_report_label is not None and source.ais_report_label != "":
			matches = True
			doctype = "tabSales Order"

		elif location == "Stores" and (len(wtype) == 0 or wtype[0].strip() != "Website")\
			and source.ais_report_label is not None and source.ais_report_label != "":
			matches = True
			doctype = "tabSales Invoice"
   		
		store_credit_payments = 0
		if matches:
			if doctype == "tabSales Order":
				sales_data = get_website_orders_sql(source.name, date, field="total_without_tax")
			elif doctype == "tabSales Invoice":
				sales_data = get_stores_sql(source.name, date, field="total_without_tax")
				store_credit_payments = get_store_credit_payments(source.name, filters.get("date"), filters.get("date"))

			if len(sales_data) > 0:
				row.update({
					"total_without_tax": sales_data[0].total_without_tax - store_credit_payments
				})
				total_without_tax += sales_data[0].total_without_tax - store_credit_payments
			else:
				row.update({
					"total_without_tax": 0.0 - store_credit_payments
				})

			row.update({
				"name": source.name,
			})
			
			#Get month to date values
			date = filters.get("date")
			selected_date = datetime.strptime(date, "%Y-%m-%d")
			start_date = datetime.strftime(selected_date, "%Y-%m-01")

			if doctype == "tabSales Order":
				sales_data = get_website_orders_sql(source.name, start_date, end_date=date, field="total_mtd")
			elif doctype == "tabSales Invoice":
				sales_data = get_stores_sql(source.name, start_date, end_date=date, field="total_mtd")
				store_credit_payments = get_store_credit_payments(source.name, start_date, selected_date)

			if len(sales_data) > 0:
				row.update({
					"total_mtd": sales_data[0].total_mtd - store_credit_payments
				})
				total_mtd += sales_data[0].total_mtd - store_credit_payments
			else:
				row.update({
					"total_mtd": 0.0 - store_credit_payments
				})
					
			# Get previous years month to date
			previous_month = selected_date + relativedelta(years=-1)
			start_date = datetime.strftime(previous_month, "%Y-%m-01")
			end_date = datetime.strftime(previous_month, "%Y-%m-%d")
   
			if doctype == "tabSales Order":
				sales_data = get_website_orders_sql(source.name, start_date, end_date=end_date, field="total_pmtd")
			elif doctype == "tabSales Invoice":
				sales_data = get_stores_sql(source.name, start_date, end_date=end_date, field="total_pmtd")
				store_credit_payments = get_store_credit_payments(source.name, start_date, end_date)
	
			if len(sales_data) > 0:
				row.update({
					"total_pmtd": sales_data[0].total_pmtd - store_credit_payments
				})
			
				total_pmtd += sales_data[0].total_pmtd - store_credit_payments
			else:
				row.update({
					"total_pmtd": 0.0 - store_credit_payments
				})

			if location == "Stores":
				#Get cash sales
				cash_sales = get_cash_sales(source.name, filters.date)
				total_cash_sales += cash_sales
				row.update({
					"cash_sales": cash_sales
				})
	
				end_of_day_closing = frappe.db.get_value("End of Day Closing", {"lead_source": source.name, "closing_date": filters.date}, ["mop_total_difference", "closing_notes", "name"], as_dict=1, order_by="creation desc")	
				if end_of_day_closing is not None:
					row.update({
						"difference": end_of_day_closing.mop_total_difference,
						"notes": end_of_day_closing.closing_notes,
						"eod_link": "<a href='/app/end-of-day-closing/{0}' target='_blank'>{1}</a>".format(end_of_day_closing.name, row.get("location"))
					})


			#Add row to data
			data.append(row)
			
	return (data, total_with_tax, total_without_tax, total_mtd, total_pmtd, total_cash_sales)

def get_website_orders_sql(source, date, end_date=None, field="total_without_tax"):
	if end_date is None:
		end_date = date

	sql = """
		SELECT 
			COALESCE(SUM(net_total), 0) AS `{field}`
		FROM
			`tabSales Order`
		JOIN
			`tabGL Entry` ON `tabSales Order`.name = `tabGL Entry`.against_voucher
		WHERE
			`tabSales Order`.source = %(source)s
			AND `tabSales Order`.transaction_date BETWEEN %(date)s AND %(end_date)s
			AND `tabSales Order`.docstatus = 1
			AND `tabGL Entry`.is_cancelled = 0
	""".format(field=field)

	return frappe.db.sql(sql, {
		"source": source,
		"date": date,
		"end_date": end_date
	}, as_dict=1)

 
def get_stores_sql(source, date, end_date=None, field="total_without_tax"):
	if end_date is None:
		end_date = date

	sql = """
		SELECT 
			COALESCE(SUM(net_total), 0) AS `{field}`
		FROM `tabSales Invoice`
		WHERE
			source = %(source)s
			AND posting_date BETWEEN %(date)s AND %(end_date)s
			AND `tabSales Invoice`.docstatus = 1
	""".format(field=field)
 
	return frappe.db.sql(sql, {"source": source, "date": date, "end_date": end_date}, as_dict=1)

def get_cash_sales(lead_source, date):
	sales_invoice_payments = frappe.db.sql("""
		SELECT COALESCE(SUM(amount), 0) - COALESCE(SUM(change_amount), 0) AS paid_amount 
		FROM `tabSales Invoice Payment`
		JOIN `tabSales Invoice` ON `tabSales Invoice`.name = `tabSales Invoice Payment`.parent
		WHERE `tabSales Invoice`.source = %s AND `tabSales Invoice`.posting_date = %s
		AND `tabSales Invoice`.docstatus = 1 AND `tabSales Invoice Payment`.mode_of_payment="Cash"
	""", (lead_source, date), as_dict=1)
 
	return sales_invoice_payments[0].paid_amount if len(sales_invoice_payments) > 0 else 0

def get_store_credit_payments(lead_source, start_date, end_date):
	sql = """
		SELECT
			si.name  AS invoice,
			sip.mode_of_payment AS mop,
			sip.amount AS amount,
			si.grand_total AS grand_total,
			si.total_taxes_and_charges AS taxes
		FROM `tabSales Invoice Payment` AS sip
		JOIN `tabSales Invoice` AS si ON si.name = sip.parent
		WHERE si.source = %s
		AND si.posting_date BETWEEN %s AND %s
		AND si.docstatus = 1
		AND si.is_pos = 1
		AND sip.mode_of_payment = "Gift Card"
	;"""
 
	store_credits = frappe.db.sql(sql, (lead_source, start_date, end_date), as_dict=1)
	net_store_credit_payments = compute_net_summaries(store_credits)
	return net_store_credit_payments

def compute_net_summaries(rows):
	store_credit_net_total = 0

	for r in rows:
		inv = r["invoice"]
		amount = r["amount"]
		gt = r["grand_total"]
		taxes = r["taxes"]
		# net factor = NT / GT = (GT - taxes) / GT
		net_factor = (gt - taxes) / gt if gt != 0 else 0
		net_part = round(amount * net_factor, 2)

		store_credit_net_total += net_part

	return store_credit_net_total

@frappe.whitelist()
def export_to_excel(date):
	from metactical.custom_scripts.utils.metactical_utils import export_query
	dates = {
		"date": date,
		"end_date": (datetime.strptime(date, "%Y-%m-%d") + relativedelta(days=1)).strftime("%Y-%m-%d")
	}

	data = {
		'report_name': 'End of Day Report - V5', 
		'file_format_type': 'Excel', 
		'filters': dates
	}

	sub_headers = ["Stores", "Online", "USA"]
	export_query(data, sub_headers)