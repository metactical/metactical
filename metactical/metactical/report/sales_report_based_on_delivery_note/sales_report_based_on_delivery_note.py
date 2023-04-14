# Copyright (c) 2023, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe

def execute(filters=None):
	columns, data = [], []
	columns = get_columns()
	data = get_data(filters)
	return columns, data
	
def get_data(filters):
	start_date = filters.get("start_date")
	end_date = filters.get("end_date")
	
	where = "AND delivery_note.posting_date BETWEEN '{}' AND '{}'".format(start_date, end_date)
	
	if filters.get("source"):
		where += " AND sales_order.source = '{}'".format(filters.get("source"))
		
	if filters.get("warehouse"):
		where += "AND dn_item.warehouse = '{}'".format(filters.get("warehouse"))
		
	data = frappe.db.sql("""SELECT
								dn_item.against_sales_order AS sales_order, sales_order.source AS order_source,
								dn_item.item_code AS item, dn_item.item_name, dn_item.qty,
								dn_item.warehouse, dn_item.amount
							FROM
								`tabDelivery Note Item` AS dn_item
							LEFT JOIN
								`tabDelivery Note` AS delivery_note ON dn_item.parent = delivery_note.name
							LEFT JOIN
								`tabSales Order` AS sales_order ON dn_item.against_sales_order = sales_order.name 
							WHERE 
								delivery_note.docstatus = 1 {where}""".format(where = where), as_dict=1)
	return data
	
	
def get_columns():
	columns = [
		{
			"fieldtype": "Link",
			"fieldname": "sales_order",
			"label": "Sales Order Number",
			"options": "Sales Order",
			"width": 150
		},
		{
			"fieldtype": "Link",
			"fieldname": "order_source",
			"label": "Order Source",
			"options": "Lead Source",
			"width": 150
		},
		{
			"fieldtype": "Link",
			"fieldname": "item",
			"label": "Item",
			"options": "Item",
			"width": 150
		},
		{
			"fieldtype": "Data",
			"fieldname": "item_name",
			"label": "Item Name",
			"width": 150
		},
		{
			"fieldtype": "Int",
			"fieldname": "qty",
			"label": "QTY",
			"width": 100
		},
		{
			"fieldtype": "Link",
			"fieldname": "warehouse",
			"label": "Delivery WHS",
			"options": "Warehouse",
			"width": 150
		},
		{
			"fieldtype": "Currency",
			"fieldname": "amount",
			"label": "Amount",
			"width": 150
		}
	]
	return columns
