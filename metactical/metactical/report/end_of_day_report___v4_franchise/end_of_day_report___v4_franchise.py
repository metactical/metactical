# Copyright (c) 2023, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
import requests
from datetime import datetime
from dateutil.relativedelta import relativedelta

def execute(filters=None):
	columns, data = [], []
	columns = get_columns(filters)
	total_with_tax = 0
	total_without_tax = 0
	total_mtd = 0
	total_pmtd = 0
	location = ""

	# get all the frachise companies and their settings
	item_search_settings = get_all_franchises()

	# get end of day report data for each franchise
	totals = []
	for i, key in enumerate(item_search_settings):
		franchise_data = get_data(item_search_settings[key], filters)
		if len(franchise_data) > 0:
			for row in franchise_data:
				if row.get("location") == "Stores Total":
					totals.append(row)
				else:
					data.append(row)
	
	# add totals to the end of the data
	data.append({})
	if len(totals) > 0:
		location = totals[0]["location"]
		total_with_tax = sum([row["total_with_tax"] for row in totals])
		total_without_tax = sum([row["total_without_tax"] for row in totals])
		total_mtd = sum([row["total_mtd"] for row in totals])
		total_pmtd = sum([row["total_pmtd"] for row in totals])

	data.append({
		"location": location, 
		"total_with_tax": total_with_tax, 
		"total_without_tax": total_without_tax,
		"total_mtd": total_mtd,
		"total_pmtd": total_pmtd
	})

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

def get_data(item_search_settings,  filters):
	data = []
	if item_search_settings.get("franchise_url") is not None and item_search_settings.get("franchise_url") != "":
		franchise_request = requests.get(item_search_settings.get("franchise_url") + "/api/method/metactical.api.end_of_day_report.get_franchise_report_data", 
						auth=(item_search_settings.api_key, item_search_settings.get_password("api_secret")),
									params={"date": filters.get("date")})

		if franchise_request.status_code == 200:
			for row in franchise_request.json().get("message", {}):
				data.append(row)

	for row in data:
		if row.get("location") == "Total Stores":
			row.update({"location": "Stores Total"})
		elif row.get("location") == "Total Websites":
			row.update({"location": "Websites Total"})
		elif row.get("location") == "USD Total":
			row.update({"location": "Total - USD"})
	
	return data

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

	sub_headers = get_all_franchises().keys()
	export_query(data, sub_headers)

	
def get_all_franchises():
	franchise_settings = frappe.get_list("Item Search Settings Franchise", "*")
	item_search_settings = {}

	# group the settings by franchise
	for setting in franchise_settings:
		franchise = setting.get("franchise_url").split(".")
		if franchise:
			item_search_settings[franchise[0][8:]] = frappe.get_doc("Item Search Settings Franchise", setting.get("name"))
	
	return item_search_settings
