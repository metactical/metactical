# Copyright (c) 2023, Techlift Technologies and contributors
# For license information, please see license.txt
import frappe

def execute(filters=None):
	columns, data = [], []
	columns = get_columns(filters)
	data = get_data(filters)
	return columns, data
	
def get_columns(filters):
	columns = [
		{
			"fieldname": "lead_source",
			"fieldtype": "Link",
			"label": "Lead Source",
			"options": "Lead Source",
			"width": 200
		},
		{
			"fieldname": "total_with_tax",
			"fieldtype": "Currency",
			"label": "Total With Tax",
			"width": 200
		},
		{
			"fieldname": "total_without_tax",
			"fieldtype": "Currency",
			"label": "Total Without tax",
			"width": 200
		},
		{
			"fieldname": "space",
			"fieldtype": "Data",
			"label": "",
			"width": 150
		},
		{
			"fieldname": "date",
			"fieldtype": "Date",
			"label": "Date",
			"width": 200
		}
	]
	return columns
	
def get_data(filters):
	data = []
	date = filters.get("date")
	sources = frappe.db.get_list("Lead Source", pluck="name")
	for source in sources:
		row = {"lead_source": source, "total_with_tax": 0, "total_without_tax": 0}
		query = frappe.db.sql("""SELECT 
									SUM(total) AS total_without_tax,
									SUM(grand_total) AS total_with_tax
								FROM
									`tabSales Invoice`
								WHERE
									source = %(source)s AND posting_date = %(date)s""",
				{"source": source, "date": date}, as_dict=1)
		if len(query) > 0:
			row.update({
				"total_with_tax": query[0].total_with_tax,
				"total_without_tax": query[0].total_without_tax
			})
		data.append(row)
	#Add date to first row
	data[0]["date"] = date
	return data
