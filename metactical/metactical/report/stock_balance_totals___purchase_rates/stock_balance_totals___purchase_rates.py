# Copyright (c) 2025, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
import requests

def execute(filters=None):
	columns, data = [], []
	columns = [
		{
			"fieldname": "location",
			"fieldtype": "Data",
			"label": "Location"
		},
		{
			"fieldname": "total",
			"fieldtype": "Currency",
			"label": "Total",
		},
		{
			"fieldname": "currency",
			"fieldtype": "Link",
			"label": "Currency",
			"options": "Currency",
			"default": "CAD"
		}
	]
	data = get_data(filters)
	return columns, data

def get_data(filters):
	data = []
	exchange_rate = requests.get("https://api.frankfurter.app/latest?amount=1&from=USD&to=CAD")
	default_currency = get_default_currency()

	data = frappe.db.sql("""
			with cte
			as
			(
				select itm.name sku, max(itm.item_name) item_name,
					max(itm.last_purchase_rate) last_purchase_rate_default_currency,
					max(itm.valuation_rate) valuation_rate,
					-- Evalumating the supplier price according to the price list currency
					max(
						case when prc.currency != %(default_currency)s then prc.price_list_rate * %(exchange_rate)s 
						else prc.price_list_rate end) supplier_price_evaluated
				
				from `tabItem` itm
				join `tabItem Price` prc on itm.name = prc.item_code and buying = 1
				where itm.ifw_ismiscitem != 1
				group by itm.name
			),
			cte2
			as
			(
				-- Fetching from the CTE joining the bin table
				select cte.sku, cte.item_name, bin.actual_qty,
				-- Using the evaluated supplier price if there is no purchase transaction
				case when last_purchase_rate_default_currency = 0 then supplier_price_evaluated else last_purchase_rate_default_currency end purchase_rate_or_supplier_price,
				bin.valuation_rate,
				bin.warehouse, whs.parent_warehouse

				from cte
				join `tabBin` bin on cte.sku = bin.item_code
				-- Join the Warehouse table to get the parent warehouse to group by
				join `tabWarehouse` whs on bin.warehouse = whs.name
				where bin.actual_qty > 0
			)
			-- At this point if there is no purchase rate or supplier price then take the valuation rate to give an accurate values
			-- Group by the parent warehouse
			select 
				cte2.parent_warehouse AS location, 
				sum(case when purchase_rate_or_supplier_price = 0 then cte2.actual_qty * valuation_rate else cte2.actual_qty * purchase_rate_or_supplier_price end) AS total,
				%(default_currency)s AS currency
			from cte2
			group by cte2.parent_warehouse;
			""", 
		{"exchange_rate": exchange_rate, "default_currency": default_currency}, as_dict=1)
	return data

def get_default_currency():
	default_company = frappe.defaults.get_user_default("Company")
	default_currency = frappe.db.get_value("Company", default_company, "default_currency")
	return default_currency