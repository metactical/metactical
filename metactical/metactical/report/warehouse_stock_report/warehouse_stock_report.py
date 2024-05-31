# Copyright (c) 2024, Techlift Technologies and contributors
# For license information, please see license.txt
# 
import frappe

def execute(filters=None):
	columns, data = [], []
	columns = get_columns()
	data = get_data(filters)
	return columns, data

def get_data(filters):
	warehouse = filters.get("warehouse")
	limit = 500
	start = 0
	bins = ["Start"]
	data = []

	excluded_items = get_cycle_counted(warehouse)

	while len(bins) > 0:
		bins = frappe.db.sql("""
			SELECT 
				ifw_retailskusuffix as retail_sku, item_name, actual_qty, `tabBin`.item_code
			FROM 
				`tabBin`
			LEFT JOIN 
				`tabItem` ON `tabItem`.item_code = `tabBin`.item_code
			WHERE 
				warehouse = %s AND actual_qty > 0
			LIMIT %s OFFSET %s
		""", (warehouse, limit, start), as_dict=1)

		for row in bins:
			if row.item_code not in excluded_items:
				data.append(row)
		start += limit
	return data

def get_cycle_counted(warehouse):
	items = []
	data = frappe.db.sql("""
			SELECT
				item.item_code
			FROM
				`tabCycle Count Item` as item
			LEFT JOIN
				`tabCycle Count` AS cycle ON cycle.name = item.parent
			WHERE
				cycle.warehouse = %(warehouse)s AND cycle.modified >= '2024-05-17 00:00:00'
				AND cycle.docstatus <> 2
			""", {"warehouse": warehouse}, as_dict=1)
	for row in data:
		items.append(row.item_code)
	return data
	

def get_columns():
	columns = [
		{
			"fieldname": "retail_sku",
			"label": "Retail SKU",
			"fieldtype": "Data",
			"width": 150
		},
		{
			"fieldname": "item_name",
			"label": "Item Name",
			"fieldtype": "Data",
			"width": 150
		},
		{
			"fieldname": "actual_qty",
			"label": "Qty",
			"fieldtype": "Int",
			"width": 150
		}
	]
	return columns

