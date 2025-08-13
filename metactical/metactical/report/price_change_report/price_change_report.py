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
			"fieldtype": "Link",
			"fieldname": "item_code",
			"label": "Item Code",
			"options": "Item",
			"width": 150
		},
		{
			"fieldtype": "Data",
			"fieldname": "retail_sku",
			"label": "Product Name",
			"width": 150
		},
		{
			"fieldtype": "Data",
			"fieldname": "item_name",
			"label": "Item name",
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
			"fieldtype": "Link",
			"fieldname": "price_list",
			"label": "Price List",
			"options": "Price List",
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
					item.item_code, item.ifw_retailskusuffix AS retail_sku, item.item_name, 
					MAX(item_barcode.barcode) AS barcode,
					CAST(version.creation AS DATE) AS date, user.full_name AS user_name,
					version.data, item_price.price_list
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
					retail_sku, item_name, user_name, data
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
			version["cost"] = get_cost(version.item_code)
			data.append(version)
	return data

def get_cost(item_code):
	# Get the default supplier from Item Defaults
	default_supplier = frappe.db.get_value(
		"Item Default", 
		{"parent": item_code, "default_supplier": ["!=", ""]}, 
		"default_supplier"
	)
	
	if not default_supplier:
		return 0
	
	supplier_price_list = frappe.db.get_value(
		"Supplier", 
		default_supplier, 
		"default_price_list"
	)
	
	if not supplier_price_list:
		return 0
		
	# Get the price from the supplier's price list for this item
	price = frappe.db.get_value(
		"Item Price", 
		{
			"item_code": item_code, 
			"price_list": supplier_price_list,
			"buying": 1
		}, 
		"price_list_rate"
	)
	
	return float(price) if price else 0