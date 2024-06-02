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
	cycle_date = filters.get("cycle_date")
	limit = 500
	start = 0
	bins = ["Start"]
	data = []

	excluded_items = get_cycle_counted(warehouse, cycle_date)

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

def get_cycle_counted(warehouse, cycle_date):
	items = []
	data = frappe.db.sql("""
			SELECT
				item.item_code
			FROM
				`tabCycle Count Item` as item
			LEFT JOIN
				`tabCycle Count` AS cycle ON cycle.name = item.parent
			WHERE
				cycle.warehouse = %(warehouse)s AND CAST(cycle.creation AS DATE) >= %(cycle_date)s
				AND cycle.docstatus <> 2
			""", {"warehouse": warehouse, "cycle_date": cycle_date}, as_dict=1)
	for row in data:
		items.append(row.item_code)
	return items
	

def get_columns():
	columns = [
		{
			"fieldname": "item_code",
			"label": "ERP SKU",
			"fieldtype": "Link",
			"options": "Item",
			"width": 150
		},
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

