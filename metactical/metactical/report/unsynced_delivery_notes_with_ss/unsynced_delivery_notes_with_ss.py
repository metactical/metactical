# Copyright (c) 2022, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe

def execute(filters=None):
	columns, data = [], []
	columns = get_columns(filters)
	data = get_data(filters)
	return columns, data
	
def get_data(filters):
	button = ""
	query = frappe.db.sql("""SELECT
										delivery_note.name AS reference, delivery_note.posting_date,
										'Not Synced With SS' AS error,
										CONCAT('<button onClick="resync_shipstation(''',delivery_note.name,''')">Resync With Shipstation</button>')
										AS action
									FROM
										`tabDelivery Note` AS delivery_note
									WHERE
										(SELECT name FROM `tabShipstation Order ID` 
											AS order_id WHERE order_id.parent = delivery_note.name
											LIMIT 1) IS NULL
										AND ((delivery_note.shipping_address_name is not NULL
										AND delivery_note.shipping_address_name != "") OR 
										(delivery_note.customer_address is not NULL AND 
										delivery_note.customer_address != '')) AND delivery_note.docstatus = 0
									""", as_dict=1)
	query2 = frappe.db.sql("""SELECT
										delivery_note.name AS reference, delivery_note.posting_date,
										'No Address' AS error
									FROM
										`tabDelivery Note` AS delivery_note
									WHERE
										(SELECT name FROM `tabShipstation Order ID` 
											AS order_id WHERE order_id.parent = delivery_note.name
											LIMIT 1) IS NULL
										AND ((delivery_note.shipping_address_name is NULL
										OR delivery_note.shipping_address_name != "") AND
										(delivery_note.customer_address is NULL OR 
										delivery_note.customer_address != ''))  AND delivery_note.docstatus = 0
									""", as_dict=1)
	data = query + query2
	return data
	
def get_columns(filters):
	columns = [
		{
			"fieldname": "reference",
			"fieldtype": "Link",
			"label": "Delivery Note",
			"options": "Delivery Note",
			"width": 200
		},
		{
			"fieldname": "posting_date",
			"fieldtype": "Date",
			"label": "Posting Date",
			"width": 200
		},
		{
			"fieldname": "error",
			"fieldtype": "Data",
			"label": "Error",
			"width": 200
		},
		{
			"fieldname": "action",
			"fieldtype": "Data",
			"width": 200
		}
	]
	return columns	
