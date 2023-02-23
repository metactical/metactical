# Copyright (c) 2023, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
import requests
from datetime import datetime
from dateutil.relativedelta import relativedelta

def execute(filters=None):
	columns, data = [], []
	columns = get_columns(filters)
	
	# Get Canada and US data
	data = get_ca_data(filters)
	us_data = get_us_data(filters)
	if len(us_data) > 0:
		data.append({})
		data.extend(us_data)
		
	return columns, data
	
def get_columns(filters):
	columns = [
		{
			"fieldname": "location",
			"fieldtype": "Location",
			"label": "Lead Source",
			"options": "Lead Source",
			"width": 200
		},
		{
			"fieldname": "total_with_tax",
			"fieldtype": "Currency",
			"label": "Total With Tax",
			"width": 120
		},
		{
			"fieldname": "total_without_tax",
			"fieldtype": "Currency",
			"label": "Total Without Tax",
			"width": 140
		},
		{
			"fieldname": "date",
			"fieldtype": "Date",
			"label": "Date",
			"width": 100
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
			"label": "MA No Tx",
			"width": 120
		},
		{
			"fieldname": "total_pmtd",
			"fieldtype": "Currency",
			"label": "PMA No Tx",
			"width": 120
		}
	]
	return columns
	
def get_ca_data(filters):
	data = []
	#Get stores data
	stores_data, total_stores_with_tax, total_stores_without_tax, stores_total_mtd, stores_total_pmtd = get_website_stores_data(filters, "Stores")
	data.extend(stores_data)
	data.append({})
	web_data, total_web_with_tax, total_web_without_tax, web_total_mtd, web_total_pmtd = get_website_stores_data(filters, "Website")
	data.extend(web_data)
	
	#Add an empty row followed with totals rows
	data.append({})
	data.append({
		"location": "Total Stores", 
		"total_with_tax": total_stores_with_tax, 
		"total_without_tax": total_stores_without_tax,
		"total_mtd": stores_total_mtd,
		"total_pmtd": stores_total_pmtd
	})
	data.append({
		"location": "Total Websites", 
		"total_with_tax": total_web_with_tax, 
		"total_without_tax": total_web_without_tax,
		"total_mtd": web_total_mtd,
		"total_pmtd": web_total_pmtd
	})
	data.append({
		"location": "CAD Total",
		"total_with_tax": total_stores_with_tax + total_web_with_tax,
		"total_without_tax": total_stores_without_tax + total_web_without_tax,
		"total_mtd": stores_total_mtd + web_total_mtd,
		"total_pmtd": stores_total_pmtd + web_total_pmtd
	})
	
	#Add date to first row
	data[0]["date"] = filters.get("date")
	return data
	
def get_website_stores_data(filters, location):
	data = []
	total_with_tax = 0
	total_without_tax = 0
	total_mtd = 0
	total_pmtd = 0
	
	date = filters.get("date")
	sources = frappe.db.get_list("Lead Source", ['name', 'ais_report_label'])
	for source in sources:
		matches = False
		doctype = ""
		date_column = ""
		wtype = source.name.split("-")
		row = {"location": source.ais_report_label, "total_with_tax": 0, "total_without_tax": 0}
		sql = ""
		
		#Check if you're getting website or stores data
		if location == "Website" and len(wtype) > 0 and wtype[0].strip() == "Website":
			matches = True
			doctype = "tabSales Order"
			date_column = "transaction_date"
		elif location == "Stores" and (len(wtype) == 0 or wtype[0].strip() != "Website"):
			matches = True
			doctype = "tabSales Invoice"
			date_column = "posting_date"
		
		if matches:
			sql = """SELECT 
						COALESCE(SUM(total), 0) AS total_without_tax,
						COALESCE(SUM(grand_total), 0) AS total_with_tax
					FROM
						`""" + doctype + """`
					WHERE
						source = %(source)s AND """ + date_column + """ = %(date)s
						AND docstatus = 1"""
			query = frappe.db.sql(sql, {"source": source.name, "date": date}, as_dict=1)
			if len(query) > 0:
				row.update({
					"total_with_tax": query[0].total_with_tax,
					"total_without_tax": query[0].total_without_tax
				})
				total_with_tax += query[0].total_with_tax
				total_without_tax += query[0].total_without_tax
			else:
				row.update({
					"total_with_tax": 0.0,
					"total_without_tax": 0.0
				})
			
			#Get month to date values
			selected_date = datetime.strptime(date, "%Y-%m-%d")
			start_date = datetime.strftime(selected_date, "%Y-%m-01")
			query = frappe.db.sql("""SELECT
										COALESCE(SUM(total), 0) AS total_mtd
									FROM
										`""" + doctype + """`
									WHERE
										source = %(source)s AND """ + date_column + """ BETWEEN %(start_date)s
										AND %(end_date)s AND docstatus = 1""",
								{"source": source.name, "start_date": start_date, "end_date": date}, as_dict=1)
			if len(query) > 0:
				row.update({
					"total_mtd": query[0].total_mtd
				})
				total_mtd += query[0].total_mtd
			else:
				row.update({
					"total_mtd": 0.0
				})
				
			# Get previous years month to date
			previous_month = selected_date + relativedelta(years=-1)
			start_date = datetime.strftime(previous_month, "%Y-%m-01")
			end_date = datetime.strftime(previous_month, "%Y-%m-%d")
			query = frappe.db.sql("""SELECT
										COALESCE(SUM(total), 0) AS total_pmtd
									FROM
										`""" + doctype + """`
									WHERE
										source = %(source)s AND """ + date_column + """ BETWEEN %(start_date)s
										AND %(end_date)s AND docstatus = 1""", 
								{"source": source.name, "start_date": start_date, "end_date": end_date}, as_dict=1)
			if len(query) > 0:
				row.update({
					"total_pmtd": query[0].total_pmtd
				})
				total_pmtd += query[0].total_pmtd
			else:
				row.update({
					"total_pmtd": 0.0
				})
				
			#Add row to data
			data.append(row)
	return data, total_with_tax, total_without_tax, total_mtd, total_pmtd 

def get_us_data(filters):
	item_search_settings = frappe.get_doc("Item Search Settings")
	us_data = []
	if item_search_settings.get("daily_report_url") is not None and item_search_settings.get("daily_report_url") != "":
		us_request = requests.get(item_search_settings.get("daily_report_url"), 
						auth=(item_search_settings.api_key, item_search_settings.api_secret),
									params={"date": filters.get("date")}, verify=False)
		if us_request.status_code == 200:
			for row in us_request.json().get("message", {}):
				us_data.append(row)
	return us_data
