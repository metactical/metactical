# Copyright (c) 2024, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe

def execute(filters=None):
	columns, data = [], []
	columns = get_columns()
	data = get_data(filters)
	return columns, data

def get_columns():
	columns = [
		{
			"label": "Item Code",
			"fieldname": "item_code",
			"fieldtype": "Link",
			"options": "Item",
			"width": 120
		},
		{
			"label": "Item Name",
			"fieldname": "item_name",
			"fieldtype": "Data",
			"width": 120
		},
		{
			"label": "Qty",
			"fieldname": "qty",
			"fieldtype": "Float",
			"width": 100
		},
		{
			"label": "Rate",
			"fieldname": "rate",
			"fieldtype": "Currency",
			"width": 100
		},
		{
			"label": "Warehouse",
			"fieldname": "warehouse",
			"fieldtype": "Link",
			"options": "Warehouse",
			"width": 120
		},
		{
			"label": "Delivery Note",
			"fieldname": "delivery_note",
			"fieldtype": "Link",
			"options": "Delivery Note",
			"width": 120
		}
	]
	return columns

def get_data(filters):
	date = filters.get("transaction_date")
	customer = filters.get("customer")
	warehouse = filters.get("warehouse")
	
	where_clause = ""
	if filters.get("delivery_note"):
		where_clause += f""" AND dn.name = '{filters.get("delivery_note")}' """

	data = frappe.db.sql(f"""
		SELECT
			dn.name AS delivery_note,
			dni.item_code,
			dni.item_name,
			dni.qty,
			dni.base_rate AS rate,
			dni.warehouse
		FROM 
			`tabDelivery Note Item` dni
		LEFT JOIN 
			`tabDelivery Note` dn ON dn.name = dni.parent
		WHERE dn.docstatus = 1 AND dni.warehouse = %(warehouse)s
		AND dn.posting_date = %(transaction_date)s
		AND dn.customer = %(customer)s
		{where_clause}
		ORDER BY dn.posting_date
	""", {"transaction_date": date, "customer": customer, "warehouse": warehouse}, as_dict=1)
	return data