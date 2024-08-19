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

	# Get Rameen data
	rameen_data = get_rameen_data(item_search_settings, filters)
	if len(rameen_data) > 0:
		# data.append({"Location": "Rameen"})
		data.extend(rameen_data)

	# Get QC1 data
	qc1_data = get_qc1_data(item_search_settings, filters)
	if len(qc1_data) > 0:
		data.append({"Location": "QC1"})
		data.extend(qc1_data)
		
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
		'report_name': 'End of Day Report - V4 Franchise', 
		'file_format_type': 'Excel', 
		'filters': dates
	}

	sub_headers = ["QC1", "Rameen"]
	export_query(data, sub_headers)

	
