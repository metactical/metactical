# Copyright (c) 2024, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
import json

def execute(filters=None):
	columns, data = [], []
	columns = get_columns()
	data = get_data(filters)
	return columns, data
	
def get_columns():
	columns = [
		{
			"fieldtype": "Data",
			"fieldname": "retail_sku",
			"label": "Retail SKU",
			"width": 150
		},
		{
			"fieldtype": "Data",
			"fieldname": "item_name",
			"label": "Retail SKU",
			"width": 150
		},
		{
			"fieldtype": "Currency",
			"fieldname": "old_price",
			"label": "Old Price",
			"width": 150
		},
		{
			"fieldtype": "Currency",
			"fieldname": "new_price",
			"label": "New Price",
			"width": 150
		},
		{
			"fieldtype": "Data",
			"fieldname": "barcode",
			"label": "Barcode",
			"width": 150
		},
		{
			"fieldtype": "Currency",
			"fieldname": "cost",
			"label": "Cost",
			"width": 150
		},
		{
			"fieldtype": "Date",
			"fieldname": "date",
			"label": "Date",
			"width": 150
		},
		{
			"fieldtype": "Data",
			"fieldname": "user_name",
			"label": "User",
			"width": 150
		}
	]
	return columns
	
def get_data(filters):
	data = []
	date = filters.get("date")
	
	versions = frappe.db.sql("""
				SELECT
					item.ifw_retailskusuffix AS retail_sku, item.item_name, 
					MAX(item_barcode.barcode) AS barcode, item.last_purchase_rate AS cost,
					CAST(version.creation AS DATE) AS date, user.full_name AS user_name,
					version.data
				FROM
					`tabVersion` AS version
				LEFT JOIN
					`tabItem Price` AS item_price ON item_price.name = version.docname
				LEFT JOIN
					`tabItem` AS item ON item.name = item_price.item_code 
				LEFT JOIN
					`tabItem Barcode` AS item_barcode ON item_barcode.parent = item.name
				LEFT JOIN
					`tabUser` AS user ON version.owner = user.name
				WHERE
					CAST(version.creation AS DATE) = %(date)s AND ref_doctype = 'Item Price'
				GROUP BY
					retail_sku, item_name, cost, user_name, data
				""", {"date": date}, as_dict=1)
				
	for version in versions:
		price_changed = False
		vdata = json.loads(version.get("data"))
		for item in vdata.get("changed", []):
			if item[0] == "price_list_rate":
				price_changed = True
				version["old_price"] = item[1]
				version["new_price"] = item[2]
		if price_changed:
			data.append(version)
	return data
