# Copyright (c) 2013, Techlift Technologies and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe

def execute(filters=None):
	columns, data = [], []
	columns = [
		{
			"fieldtype": "Date",
			"fieldname": "transaction_date",
			"label": "Date",
			"width": 100
		},
		{
			"fieldtype": "Data",
			"fieldname": "po_no",
			"label": "Customer Purchase Order",
			"width": 100
		},
		{
			"fieldtype": "Link",
			"options": "Sales Order",
			"fieldname": "sales_order",
			"label": "Sales Order #",
			"width": 150
		},
		{
			"fieldtype": "Data",
			"fieldname": "pick_list_printed",
			"label": "Pick List Printed",
			"width": 100
		},
		{
			"fieldtype": "Datetime",
			"fieldname": "print_time",
			"label": "Pick List Printed Date",
			"width": 100
		},
		{
			"fieldtype": "Data",
			"fieldname": "pick_list_packed",
			"label": "Pick List Packed",
			"width": 100
		},
		{
			"fieldtype": "Data",
			"fieldname": "pick_list_cancelled",
			"label": "Pick List Cancelled",
			"width": 100
		},
		{
			"fieldtype": "Datetime",
			"fieldname": "cancel_date",
			"label": "Pick List Cancelled Date",
			"width": 100
		},
		{
			"fieldtype": "Data",
			"fieldname": "pick_list_notes",
			"label": "Reason for Cancelation",
			"width": 150
		},
		{
			"fieldtype": "Data",
			"fieldname": "notes",
			"label": "Notes",
			"width": 100
		},
		{
			"fieldtype": "Link",
			"options": "Pick List",
			"fieldname": "pick_list",
			"label": "Pick List #",
			"width": 150
		},
		{
			"fieldtype": "Data",
			"fieldname": "tracking_no",
			"label": "Tracking No",
			"width": 150
		},
		{
			"fieldtype": "Data",
			"fieldname": "status",
			"label": "Order Status",
			"width": 100
		},
		{
			"fieldtype": "Data",
			"fieldname": "source",
			"label": "Source of Website",
			"width": 100
		}
	]
	
	sales_orders = get_sales_orders(filters)
	pick_lists = get_pick_lists(filters, sales_orders)
	data = get_packed(pick_lists)
	return columns, data
	

def get_sales_orders(filters):
	
	where_filter = {"from_date": filters.from_date, "to_date": filters.to_date}
	where = ''
	
	if filters.source:
		where = " AND source = %(source)s"
		where_filter.update({"source": filters.source})
	
	ret = frappe.db.sql('''SELECT 
								name, source, status, transaction_date, po_no
							FROM 
								`tabSales Order` 
							WHERE 
								transaction_date BETWEEN %(from_date)s AND %(to_date)s 
								AND docstatus = 1''' + where, where_filter, as_dict=1)
	return ret

def get_pick_lists(filters, sales_orders):
	data = []
	if sales_orders:
		for order in sales_orders:
			quaried_picks = []
			picks = frappe.db.sql('''
									SELECT 
										parent AS pick_list 
									FROM 
										`tabPick List Item`  
									WHERE 
										`tabPick List Item`.sales_order = %(sales_order)s
								''', {"sales_order": order.name}, as_dict=1)
			if not picks:
				#If there are no pick lists associated with the Sales Order
				sdata = {
					"transaction_date": order.transaction_date, 
					"sales_order": order.name, 
					"status": order.status, 
					"pick_list_printed": "No Picklist", 
					"pick_list_cancelled": "No Picklist",
					"delivery": None,
					"po_no": order.po_no}
				data.append(sdata)	
			else:
				for pick in picks:
					if pick not in quaried_picks:
						quaried_picks.append(pick)
						ret = frappe.db.sql('''SELECT
													pick_list.name AS pick_list,
													pick_list.date AS pick_list_date,
													pick_list.print_date_time AS print_time,
													CASE
														WHEN pick_list.print_date_time IS NOT NULL THEN 'Yes'
														ELSE 'No'
													END AS pick_list_printed,
													CASE
														WHEN pick_list.docstatus = 2 THEN 'Yes'
														ELSE 'No'
													END AS pick_list_cancelled,
													delivery_note.lr_no AS tracking_no,
													pick_list.pick_list_cancel_date AS cancel_date,
													pick_list.cancel_reason AS pick_list_notes,
													notes,
													delivery_note.name AS delivery
												FROM 
													`tabPick List` AS pick_list
												LEFT JOIN
													`tabDelivery Note` AS delivery_note ON delivery_note.pick_list = pick_list.name
												WHERE
													pick_list.name = %(pick_list)s''', {"pick_list": pick.pick_list}, as_dict=1)
																				
						for pick_list in ret:
							if not pick_list['notes']:
								pick_list.update({"notes": '<button class="btn btn-xs btn-default" onClick="add_notes(\'' + pick_list['pick_list'] + '\')">Add Notes</button>'})
							sdata = {"transaction_date": order.transaction_date, "sales_order": order.name, "status": order.status, "po_no": order.po_no}												
							sdata.update(pick_list)
							data.append(sdata)
	return data
	
def get_packed(delivery_notes):
	if delivery_notes:
		for delivery_note in delivery_notes:
			if delivery_note['delivery']:
				ret = frappe.db.sql('''SELECT name FROM `tabPacking Slip` WHERE delivery_note = %(delivery_note)s''', {"delivery_note": delivery_note['delivery']}, as_dict=1)
				
				if ret:
					delivery_note.update({"pick_list_packed": 'Yes'})
				else:
					delivery_note.update({"pick_list_packed": 'No'})
			else:
				delivery_note.update({"pick_list_packed": "No Delivery Note"})
	return delivery_notes



@frappe.whitelist()
def insert_notes(**args):
	args = frappe._dict(args)
	doc = frappe.get_doc('Pick List', args.pick_list)
	doc.db_set("notes", args.notes, notify=True)
	return "Success"
