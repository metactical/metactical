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
			"fieldtype": "Link",
			"fieldname": "reference_type",
			"label": "Reference Type",
			"options": "Doctype",
			"width": 150
		},
		{
			"fieldtype": "Dynamic Link",
			"fieldname": "reference",
			"label": "Reference",
			"options": "reference_type",
			"width": 150
		},
		{
			"fieldtype": "Link",
			"fieldname": "customer",
			"label": "Customer",
			"options": "Customer",
			"width": 150
		},
		{
			"fieldtype": "Data",
			"fieldname": "source",
			"label": "Source",
			"width": 150
		},
		{
			"fieldtype": "Curreny",
			"fieldname": "base_grand_total",
			"label": "Total",
			"width": 150
		},
		{
			"fieldtype": "Date",
			"fieldname": "posting_date",
			"label": "Date",
			"width": 150
		},
		{
			"fieldtype": "Check",
			"fieldname": "is_return",
			"label": "Is Return",
			"width": 150
		},
		{
			"fieldtype": "Check",
			"fieldname": "ifw_is_store_credit",
			"label": "Is Store Credit",
			"options": "Sales Invoice",
			"width": 150
		}
	]
	return columns
	
	
def get_data(filters):
	where = ""
	if filters.get("source"):
		where += f" AND source = '{filters.get('source')}'"
	invoice_data = frappe.db.sql(f"""
				SELECT 
					'Sales Invoice' AS reference_type, name AS reference, customer AS customer, ABS(base_grand_total) AS base_grand_total, 
					posting_date, is_return, ifw_is_store_credit, source
				FROM 
					`tabSales Invoice`
				WHERE 
					is_return = 1 AND is_pos <> 1
					AND posting_date BETWEEN %(from_date)s AND %(to_date)s
				{where}
				ORDER BY
					source, customer
			""",
			{"from_date": filters.get("from_date"), "to_date": filters.get("to_date")}, as_dict=1)
			
	delivery_data = frappe.db.sql(f"""
				SELECT 
					'Delivery Note' AS reference_type, name AS reference, customer AS customer, 
					ABS(base_grand_total) AS base_grand_total, 
					posting_date, is_return, source
				FROM 
					`tabDelivery Note`
				WHERE 
					is_return = 1
					AND posting_date BETWEEN %(from_date)s AND %(to_date)s
				{where}
				ORDER BY
					source, customer
			""",
			{"from_date": filters.get("from_date"), "to_date": filters.get("to_date")}, as_dict=1)
	data = invoice_data + delivery_data
	return data
