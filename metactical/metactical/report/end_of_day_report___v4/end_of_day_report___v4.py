# Copyright (c) 2023, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
import requests
from datetime import datetime
from dateutil.relativedelta import relativedelta

def execute(filters=None):
	columns, data = [], []
	columns = get_columns(filters)
	item_search_settings = frappe.get_doc("Item Search Settings")

	# Get Canada and US data
	data = get_ca_data(filters)

	# Get USA data
	us_data = get_us_data(item_search_settings, filters)

	if len(us_data) > 0:
		data.append({"Location": "USA"})
		data.extend(us_data)

	###### ------ New report (End of Day Report - v4 Franchise) created for qc1 and rameen data ------ ###### 
	
	# # Get Rameen data
	# rameen_data = get_rameen_data(item_search_settings, filters)
	# if len(rameen_data) > 0:
	# 	data.append({"Location": "Rameen"})
	# 	data.extend(rameen_data)

	# # Get QC1 data
	# qc1_data = get_qc1_data(item_search_settings, filters)
	# if len(qc1_data) > 0:
	# 	data.append({"Location": "QC1"})
	# 	data.extend(qc1_data)
		
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
	#Get stores data
	# data.append({"Location": "Stores"})
	stores_data, total_stores_with_tax, total_stores_without_tax, stores_total_mtd, stores_total_pmtd = get_website_stores_data(filters, "Stores")
	
	# sort the data based on the array given
	order = [ "Store - Camo - Downtown", "Store - Camo - Edmonds", "Store - Camo - Victoria","Store - Camo - Queen", "Store - Gorilla - Vancouver"]
	stores_data = sorted(stores_data, key=lambda x: order.index(x.get("name")))
	data.extend(stores_data)

	data.append({"Location": "Online"})
	web_data, total_web_with_tax, total_web_without_tax, web_total_mtd, web_total_pmtd = get_website_stores_data(filters, "Website")

	order = ["Website - RAS", "Website - Camo", "Website - Gorilla", "Website - GPD"]
	web_data = sorted(web_data, key=lambda x: order.index(x.get("name")))
	data.extend(web_data)
	
	#Add an empty row followed with totals rows
	data.append({})
	data.append({
		"location": "Stores - Total", 
		"total_with_tax": total_stores_with_tax, 
		"total_without_tax": total_stores_without_tax,
		"total_mtd": stores_total_mtd,
		"total_pmtd": stores_total_pmtd
	})
	data.append({
		"location": "Websites - Total", 
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
	
	return data
	
def get_website_stores_data(filters, location):
	data = []
	total_with_tax = 0
	total_without_tax = 0
	total_mtd = 0
	total_pmtd = 0
	
	date = filters.get("date")
	sources = frappe.db.get_list("Lead Source", 
									['name', 'ais_report_label'], 
									{
										"name": ["not in", ["Website - Valley", "Website - MRK", "Website - Zelen", "Website - RASUSA", "Store - Camo - Montreal"]]
									})
	for source in sources:
		matches = False
		doctype = ""
		date_column = ""
		wtype = source.name.split("-")
		row = {"location": source.ais_report_label, "total_with_tax": 0, "total_without_tax": 0}
		sql = ""
		
		#Check if you're getting website or stores data
		if location == "Website" and len(wtype) > 0 and wtype[0].strip() == "Website" \
			and source.ais_report_label is not None and source.ais_report_label != "":
			matches = True
			doctype = "tabSales Order"

		elif location == "Stores" and (len(wtype) == 0 or wtype[0].strip() != "Website")\
			and source.ais_report_label is not None and source.ais_report_label != "":
			matches = True
			doctype = "tabSales Invoice"
		
		if matches:
			sql = """SELECT 
						COALESCE(SUM(total), 0) AS total_without_tax
					FROM
						`""" + doctype + """`
					WHERE
						source = %(source)s AND neb_payment_completed_at = %(date)s
						AND docstatus = 1"""

			query = frappe.db.sql(sql, {"source": source.name, "date": date}, as_dict=1)
			if len(query) > 0:
				row.update({
					"total_without_tax": query[0].total_without_tax
				})
				total_without_tax += query[0].total_without_tax
			else:
				row.update({
					"total_without_tax": 0.0
				})

			row.update({
				"name": source.name,
			})
			
			#Get month to date values
			selected_date = datetime.strptime(date, "%Y-%m-%d")
			start_date = datetime.strftime(selected_date, "%Y-%m-01")
			query = frappe.db.sql("""SELECT
										COALESCE(SUM(total), 0) AS total_mtd
									FROM
										`""" + doctype + """`
									WHERE
										source = %(source)s AND neb_payment_completed_at BETWEEN %(start_date)s
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
										source = %(source)s AND neb_payment_completed_at BETWEEN %(start_date)s
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

def get_us_data(item_search_settings, filters):
	us_data = []
	
	if item_search_settings.get("daily_report_url") is not None and item_search_settings.get("daily_report_url") != "":
		us_request = requests.get(item_search_settings.get("daily_report_url"), 
						auth=(item_search_settings.api_key, item_search_settings.get_password("api_secret")),
									params={"date": filters.get("date")})

		if us_request.status_code == 200:
			for row in us_request.json().get("message", {}):
				us_data.append(row)
	
	for row in us_data:
		if row.get("location") == "Total Stores":
			row.update({"location": "Stores Total"})
		elif row.get("location") == "Total Websites":
			row.update({"location": "Websites Total"})
		elif row.get("location") == "USD Total":
			row.update({"location": "Total - USD"})

	return us_data

def get_rameen_data(item_search_settings,  filters):
	item_search_settings = frappe.get_doc("Item Search Settings")
	rameen_data = []
	if item_search_settings.get("rameen_daily_report_url") is not None and item_search_settings.get("rameen_daily_report_url") != "":
		us_request = requests.get(item_search_settings.get("rameen_daily_report_url"), 
						auth=(item_search_settings.rameen_api_key, item_search_settings.get_password("rameen_api_secret")),
									params={"date": filters.get("date")})

		if us_request.status_code == 200:
			for row in us_request.json().get("message", {}):
				rameen_data.append(row)

	for row in rameen_data:
		if row.get("location") == "Total Stores":
			row.update({"location": "Stores Total"})
		elif row.get("location") == "Total Websites":
			row.update({"location": "Websites Total"})
		elif row.get("location") == "USD Total":
			row.update({"location": "Total - USD"})
	
	return rameen_data

def get_qc1_data(item_search_settings, filters):
	qc1_data = []
	if item_search_settings.get("qc1_daily_report_url") is not None and item_search_settings.get("qc1_daily_report_url") != "":
		us_request = requests.get(item_search_settings.get("qc1_daily_report_url"), 
						auth=(item_search_settings.qc1_api_key, item_search_settings.get_password("qc1_api_secret")),
									params={"date": filters.get("date")})

		if us_request.status_code == 200:
			for row in us_request.json().get("message", {}):
				qc1_data.append(row)

	for row in qc1_data:
		if row.get("location") == "Total Stores":
			row.update({"location": "Stores Total"})
		elif row.get("location") == "Total Websites":
			row.update({"location": "Websites Total"})
		elif row.get("location") == "USD Total":
			row.update({"location": "Total - USD"})
	
	return qc1_data

@frappe.whitelist()
def export_to_excel(date):
	from metactical.custom_scripts.utils.metactical_utils import export_query

	dates = {
		"date": date,
		"end_date": (datetime.strptime(date, "%Y-%m-%d") + relativedelta(days=1)).strftime("%Y-%m-%d")
	}

	data = {
		'report_name': 'End of Day Report - V4', 
		'file_format_type': 'Excel', 
		'filters': dates
	}

	sub_headers = ["Stores", "Online", "USA", "QC1", "Rameen"]
	export_query(data, sub_headers)

	
