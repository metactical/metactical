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
			"label": "Sales Order",
			"width": 150
		},
		{
			"fieldtype": "Data",
			"fieldname": "status",
			"label": "Status",
			"width": 100
		},
		{
			"fieldtype": "Data",
			"fieldname": "source",
			"label": "Website",
			"width": 100
		},
		{
			"fieldtype": "Link",
			"options": "Pick List",
			"fieldname": "pick_list",
			"label": "Pick List",
			"width": 150
		},
		{
			"fieldtype": "Data",
			"fieldname": "pick_list_printed",
			"label": "Pick List Printed",
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
			"fieldtype": "Data",
			"fieldname": "tracking_no",
			"label": "Tracking No",
			"width": 150
		},
		{
			"fieldtype": "Data",
			"fieldname": "pick_list_notes",
			"label": "Pick List Notes",
			"width": 150
		}
	]
	
	sales_orders = get_sales_orders(filters)
	data = get_pick_lists(filters, sales_orders)
	return columns, data
	

def get_sales_orders(filters):
	
	where_filter = {"from_date": filters.from_date, "to_date": filters.to_date}
	where = ''
	
	if filters.source:
		where = " AND source = %(source)s"
		where_filter.update({"source": filters.source})
	
	ret = frappe.db.sql('''SELECT 
								name, source, status, transaction_date
							FROM 
								`tabSales Order` 
							WHERE 
								transaction_date BETWEEN %(from_date)s AND %(to_date)s 
								AND status IN ('To Deliver', 'To Deliver and Bill') ''' + where, where_filter, as_dict=1)
	return ret

def get_pick_lists(filters, sales_orders):
	data = []
	if sales_orders:
		for order in sales_orders:			
			ret = frappe.db.sql('''SELECT
										pick_list.name AS pick_list,
										pick_list.date AS pick_list_date,
										pick_list.po_no,
										CASE
											WHEN pick_list.print_date_time IS NOT NULL THEN 'Yes'
											ELSE 'No'
										END AS pick_list_printed,
										CASE
											WHEN pick_list.docstatus = 2 THEN 'Yes'
											ELSE 'No'
										END AS pick_list_cancelled,
										delivery_note.lr_no AS tracking_no,
										pick_list.cancel_reason AS pick_list_notes
									FROM 
										`tabPick List` AS pick_list
									LEFT JOIN
										`tabDelivery Note` AS delivery_note ON delivery_note.pick_list = pick_list.name
									WHERE
										pick_list.name IN (SELECT DISTINCT parent 
																FROM 
																	`tabPick List Item`  
																WHERE 
																	`tabPick List Item`.sales_order = %(sales_order)s
																GROUP BY parent)''', {"sales_order": order.name}, as_dict=1)
																	
			for pick_list in ret:
				sdata = {"transaction_date": order.transaction_date, "sales_order": order.name, "status": order.status}													
				sdata.update(pick_list)
				data.append(sdata)
	return data
