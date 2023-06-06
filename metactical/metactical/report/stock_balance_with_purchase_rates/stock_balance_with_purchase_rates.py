# Copyright (c) 2023, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
import requests


def execute(filters=None):
	columns, data = [], []
	columns = get_columns()
	data = get_data()
	return columns, data
	
def get_data():
	data = []
	exchange_rate = requests.get("https://api.frankfurter.app/latest?amount=1&from=USD&to=CAD")
	#return exchange_rate.json()
	if exchange_rate.json():
		exchange_rate = exchange_rate.json().get("rates").get("CAD")
		data = frappe.db.sql("""
							WITH cte
							AS
							(
								SELECT 
									itm.name sku, max(itm.item_name) item_name,
									max(itm.last_purchase_rate) last_purchase_rate_CAD,
									-- Evaluating the supplier price according to the price list currency
									max(case when prc.currency = 'USD' then prc.price_list_rate * %(usd_rate)s else prc.price_list_rate end) supplier_price_evaluated
								FROM 
									`tabItem` itm
								LEFT JOIN 
									`tabItem Price` prc on itm.name = prc.item_code and buying = 1
								GROUP BY 
									itm.name
							)
							-- Fetching from the CTE joining the bin table
							SELECT 
								cte.sku, cte.item_name, sum(bin.actual_qty) qty_all_warehouse,
								-- Using the evaluated supplier price if there is no purchase transaction
								max(case when last_purchase_rate_CAD = 0 then supplier_price_evaluated else last_purchase_rate_CAD end) purchase_rate_or_supplier_price
							FROM 
								cte
							JOIN
								`tabBin` bin on cte.sku = bin.item_code
							GROUP BY 
								sku
							""", {'usd_rate': exchange_rate}, as_dict=1)
	return data
	
def get_columns():
	columns = [
		{
			"fieldname": "sku",
			"fieldtype": "Data",
			"label": "SKU",
			"width": "150"
		},
		{
			"fieldname": "item_name",
			"fieldtype": "Data",
			"label": "Item Name",
			"width": "150"
		},
		{
			"fieldname": "qty_all_warehouse",
			"fieldtype": "Int",
			"label": "All Warehouse Qty",
			"width": "150"
		},
		{
			"fieldname": "purchase_rate_or_supplier_price",
			"fieldtype": "Currency",
			"label": "Purchase Rate/ Supplier Price",
			"width": "200"
		}
	]
	return columns
