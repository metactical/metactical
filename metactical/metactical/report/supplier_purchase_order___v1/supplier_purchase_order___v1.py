# Copyright (c) 2024, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
import json

def execute(filters=None):
	columns = get_columns()
	limit = filters.get("limit")
	conditions = get_conditions(filters)
	data = get_data(conditions)

	for d in data:
		d["po_order_id"] = f'<a href="/app/purchase-order/{d["po_order_id"]}">{d["po_order_id"]}</a>'

	return columns, data

def get_conditions(filters):
	conditions = []

	if filters.get("from_date"):
		conditions.append("po.transaction_date >= '{from_date}'".format(from_date=filters.get("from_date")))
	if filters.get("to_date"):
		conditions.append("po.transaction_date <= '{to_date}'".format(to_date=filters.get("to_date")))
	if filters.get("supplier"):
		conditions.append("supplier = '{supplier}'".format(supplier=filters.get("supplier")))
	if filters.get("item_code"):
		conditions.append("poi.item_code = '{item_code}'".format(item_code=filters.get("item_code")))

	conditions = "WHERE " + " AND ".join(conditions) if conditions else ""
	if filters.get("limit") and filters.get("limit") != "All":
		conditions += " limit {}".format(filters.get("limit"))
	
	return conditions

def get_data(conditions):
	purchase_orders = frappe.db.sql("""
		SELECT
			poi.item_code,
			pri.ifw_retailskusuffix AS retail_sku,
			po.transaction_date AS purchase_order_date,
			po.name AS po_order_id,
			poi.qty AS quantity,
			pri.warehouse,
			poi.supplier_part_no AS supplier,
			(SELECT transaction_date FROM `tabPurchase Receipt` pr WHERE (pr.name = pri.parent and pri.docstatus=1)) AS purchase_order_receive_date
		FROM
			`tabPurchase Order Item` poi
		JOIN
			`tabPurchase Order` po ON po.name = poi.parent
		LEFT JOIN
			`tabPurchase Receipt Item` pri ON poi.name = pri.purchase_order_item
		{conditions}
	""".format(conditions=conditions), as_dict=True)
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
		"label": "Supplier Code",
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