# Copyright (c) 2024, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
import json

def execute(filters=None):
	columns = get_columns()
	print(filters)
	limit = filters.get("limit")
	filters = get_conditions(filters)
	data = get_data(filters, limit)

	for d in data:
		d["po_order_id"] = f'<a href="/app/purchase-order/{d["po_order_id"]}">{d["po_order_id"]}</a>'

	return columns, data

def get_conditions(filters):
	# from_date, to_date, supplier, item_code, retail_sku
	conditions = []

	if filters.get("from_date"):
		conditions.append("po.transaction_date >= '{from_date}'".format(from_date=filters.get("from_date")))
	if filters.get("to_date"):
		conditions.append("po.transaction_date <= '{to_date}'".format(to_date=filters.get("to_date")))
	if filters.get("supplier"):
		conditions.append("supplier = '{supplier}'".format(supplier=filters.get("supplier")))
	if filters.get("item_code"):
		conditions.append("poi.item_code = '{item_code}'".format(item_code=filters.get("item_code")))
	if filters.get("retail_sku"):
		conditions.append("`tabItem`.ifw_retailskusuffix = '{retail_sku}'".format(retail_sku=filters.get("retail_sku")))
	
	return "WHERE " + " AND ".join(conditions) if conditions else ""

def get_data(filters, limit):
	purchase_orders = frappe.db.sql("""
		SELECT
			poi.item_code,
			pri.ifw_retailskusuffix AS retail_sku,
			po.transaction_date AS purchase_order_date,
			po.name AS po_order_id,
			poi.qty AS quantity,
			pri.warehouse,
			(SELECT posting_date FROM `tabPurchase Receipt` WHERE name = pri.parent) AS purchase_order_receive_date,
			(SELECT supplier FROM `tabPurchase Order` WHERE name = poi.parent) AS supplier
		FROM
			`tabPurchase Order Item` poi
		JOIN
			`tabPurchase Order` po ON po.name = poi.parent
		LEFT JOIN
			`tabPurchase Receipt Item` pri ON poi.name = pri.purchase_order_item
		{filters}
		limit {limit}
	""".format(filters=filters, limit=limit), as_dict=True)
	return purchase_orders

def get_columns():
	return [{
		"label": "Item Code",
		"fieldname": "item_code",
		"fieldtype": "Data",
		"width": 100
	}, {
		"label": "Retail SKU",
		"fieldname": "retail_sku",
		"fieldtype": "Data",
		"width": 100
	}, {
		"label": "Supplier",
		"fieldname": "supplier",
		"fieldtype": "Data",
		"width": 100
	}, {
		"label": "Purchase Order Date",
		"fieldname": "purchase_order_date",
		"fieldtype": "Date",
		"width": 100
	}, {
		"label": "Purchase Order Receive Date",
		"fieldname": "purchase_order_receive_date",
		"fieldtype": "Date",
		"width": 100
	}, {
		"label": "PO Order ID",
		"fieldname": "po_order_id",
		"fieldtype": "Data",
		"width": 100
	}, {
		"label": "Quantity",
		"fieldname": "quantity",
		"fieldtype": "Int",
		"width": 100
	}, {
		"label": "Warehouse",
		"fieldname": "warehouse",
		"fieldtype": "Data",
		"width": 100
	}]