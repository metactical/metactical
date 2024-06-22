# Copyright (c) 2024, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
from metactical.custom_scripts.warehouse.warehouse import get_item_details2

def execute(filters=None):
	purchase_orders = filters.get("purchase_order") if filters.get("purchase_order") else None
	supplier = filters.get("supplier") if filters.get("supplier") else None
	sales_orders = filters.get("sales_order") if filters.get("sales_order") else None
	price_lists = filters.get("price_list") if filters.get("price_list") else []
	costs = {}

	if not supplier and not purchase_orders and not sales_orders:
		return [], []

	if supplier:
		supplier_price_list = frappe.db.get_value("Supplier", supplier, "default_price_list")
		if (supplier_price_list):
			price_lists.append(supplier_price_list)

	elif purchase_orders:
		supplier_price_list = frappe.db.get_values("Purchase Order", {"name": ['in', purchase_orders]}, "buying_price_list")
		if (supplier_price_list):
			supplier_price_list = [item[0] for item in supplier_price_list]

			# remove duplicates from supplier_price_list
			supplier_price_list = list(set(supplier_price_list)) 
			price_lists += supplier_price_list
	
	elif sales_orders:
		supplier_price_list = []
		for so in sales_orders:
			items = frappe.get_doc("Sales Order", so).items
			for item in items:
				suppliers = frappe.get_list("Item Supplier", filters={"parent": item.item_code}, fields=["supplier"])
				
				cost, currrency, camfrn = get_item_details2(item.item_code, suppliers)
				costs[item.item_code] = cost

	columns = get_columns(price_lists, supplier_price_list, sales_orders, purchase_orders, costs)
	data = get_data(supplier, purchase_orders, sales_orders, price_lists, supplier_price_list, costs)
	return columns, data

def get_data(supplier, purchase_orders, sales_orders, price_lists, supplier_price_list=None, costs=None):
	items_list = []
	items = []

	if supplier:
		items = frappe.db.sql(""" SELECT item_code, variant_of, ifw_retailskusuffix, item_name, ifw_duty_rate
									FROM `tabItem Supplier`
									JOIN `tabItem` on item_code = `tabItem Supplier`.parent
									WHERE supplier = %s """, supplier, as_dict=True)

		items_list = [item["item_code"] for item in items]
	elif purchase_orders:
		items = frappe.db.sql(""" SELECT poi.item_code, i.variant_of, i.ifw_retailskusuffix, i.item_name, poi.parent, i.ifw_duty_rate
									FROM `tabPurchase Order Item` poi
									JOIN `tabItem` i on i.name = poi.item_code
									WHERE poi.parent IN %s """, (purchase_orders,), as_dict=True)

		items_list = [item["item_code"] for item in items]

	elif sales_orders:
		items = frappe.db.sql(""" SELECT soi.item_code, i.variant_of, i.ifw_retailskusuffix, i.item_name, soi.parent, i.ifw_duty_rate
									FROM `tabSales Order Item` soi
									JOIN `tabItem` i on i.name = soi.item_code
									WHERE soi.parent IN %s """, (sales_orders,), as_dict=True)

		items_list = [item["item_code"] for item in items]
	
	
	item_prices = frappe.db.get_list("Item Price", 
										filters={"price_list": ["in", price_lists], "item_code": ["in", items_list]}, 
										fields=["item_code", "price_list_rate", "price_list"]
									)

	# Create a dictionary of item prices for easy access
	# item_prices_dict = {
	# 	"item_code": {
	# 		"price_list": price_list_rate
	# 	}
	# }

	item_prices_dict = {}
	for item_price in item_prices:
		if item_price["item_code"] not in item_prices_dict:
			item_prices_dict[item_price["item_code"]] = {}
		item_prices_dict[item_price["item_code"]][item_price["price_list"]] = item_price["price_list_rate"]
	
	# Prepare data for the report
	data = []
	for item in items:
		data.append({
			"purchase_order": item["parent"] if "parent" in item else "",
			"erpsku": item["item_code"],
			"templatesku": item["variant_of"],
			"retail_sku": item["ifw_retailskusuffix"],
			"item_name": item["item_name"],
			"ifw_duty_rate": item["ifw_duty_rate"],
			"cost": costs[item['item_code']] if item["item_code"] in costs else "",
			"alc": ""
		})

		if item["item_code"] in item_prices_dict:
			for price_list in price_lists:			
				price_list_column = price_list.lower().replace("-", "").replace("  ", "_").replace(" ", "_")
				data[-1][price_list_column] = item_prices_dict[item["item_code"]].get(price_list, "")

	return data


def get_columns(price_lists, supplier_price_lists, sales_orders, purchase_orders, cost):
	# ERPSKU | TemplateSKU | Retail SKU | Item Name | SUP - Supplier Price List | ALC | RET - CamoFRN - CAD | RET - Camo | RET - Gorilla
	columns = []
	if type(supplier_price_lists) == list and len(supplier_price_lists) > 0:
		columns.append({
			"label": "Purchase Order" if purchase_orders else "Sales Order" if sales_orders else "",
			"fieldtype": "Link",
			"fieldname": "purchase_order",
			"options": "Purchase Order" if purchase_orders else "Sales Order" if sales_orders else ""
		})

	columns.extend([{
		"label": "ERPSKU",
		"fieldtype": "Data",
		"fieldname": "erpsku",
		"width": 120
	},
	{
		"label": "TemplateSKU",
		"fieldtype": "Data",
		"fieldname": "templatesku",
		"width": 120
	},
	{
		"label": "Retail SKU",
		"fieldtype": "Data",
		"fieldname": "retail_sku",
		"width": 120
	},
	{
		"label": "Item Name",
		"fieldtype": "Data",
		"fieldname": "item_name",
		"width": 120
	},
	{
		"label": "Duty Rate",
		"fieldtype": "Float",
		"fieldname": "ifw_duty_rate",
		"width": 120
	}])

	if cost:
		columns.append({
			"label": "Cost",
			"fieldtype": "Data",
			"fieldname": "cost",
			"width": 120
		})
	elif supplier_price_lists:
		if type(supplier_price_lists) == str:
			supplier_price_lists = [supplier_price_lists]

		for spl in supplier_price_lists:
			price_list_column = spl.lower().replace("-", "").replace("  ", "_").replace(" ", "_")
			columns.append({
				"label": spl,
				"fieldtype": "Data",
				"fieldname": price_list_column,
				"width": 120,
				"default": ""
			})
	
	columns.append({
		"label": "ALC",
		"fieldtype": "Data",
		"fieldname": "alc",
		"width": 120
	})

	for price_list in price_lists:
		price_list_column = price_list.lower().replace("-", "").replace("  ", "_").replace(" ", "_")
		if price_list in supplier_price_lists:
			continue

		column = {
			"label": price_list,
			"fieldtype": "Data",
			"fieldname": price_list_column,
			"width": 120,
			"default": ""
		}
		columns.append(column)

	return columns