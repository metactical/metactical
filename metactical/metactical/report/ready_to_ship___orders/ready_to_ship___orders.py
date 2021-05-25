# Copyright (c) 2013, Techlift Technologies and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe

def execute(filters=None):
	columns, data = [], []
	columns = [
		{
			"label": "Sales Order",
			"fieldname": "sales_order",
			"fieldtype": "Link",
			"options": "Sales Order",
		},
		{
			"label": "Customer Purchase Order Number",
			"fieldname": "po_no",
			"fieldtype": "Data",
		},
		{
			"label": "Date",
			"fieldname": "transaction_date",
			"fieldtype": "Date"
		},
		{
			"label": "Pick List Printed",
			"fieldname": "pick_list_print",
			"fieldtype": "Datetime",
			"width": 150
		},
		{
			"label": "Warehouse",
			"fieldname": "warehouse",
			"fieldtype": "Link",
			"options": "Warehouse"
		},
		{
			"label": "Status",
			"fieldname": "STATUS",
			"fieldtype": "Data"
		},
		{
			"label": "Tag",
			"fieldname": "tag",
			"fieldtype": "Data"
		},
		{
			"label": "Source",
			"fieldname": "source",
			"fieldtype": "Link",
			"options": "Lead Source"
		},
		{
			"label": "Customer",
			"fieldname": "customer",
			"fieldtype": "Link",
			"options": "Customer",
		}
	]
	
	where = ''
	where_filter = {}
	
	if filters.from_date and filters.to_date:
		where = ' AND so.transaction_date BETWEEN %(from_date)s AND %(to_date)s '
		where_filter.update({'from_date': filters.from_date, 'to_date': filters.to_date})
		
	if filters.source:
		where = ' AND so.source = %(source)s '
		where_filter.update({'source': filters.source})
	
	query = frappe.db.sql('''
							SELECT
								so.name AS sales_order,
								so.po_no,
								so.transaction_date,
								so.set_warehouse AS warehouse,
								so.STATUS,
								(select GROUP_CONCAT(tag SEPARATOR ', ') from `tabTag Link` tl where tl.parent = soi.parent) as tag,
								so.source,
								so.customer
							FROM
								`tabSales Order Item` soi
								LEFT JOIN `tabBin` bin ON soi.item_code = bin.item_code
								LEFT JOIN `tabSales Order` so ON soi.parent = so.NAME
							WHERE
								( bin.actual_qty ) > 0 
								AND ( so.STATUS = "To Deliver" OR so.STATUS = "To Deliver and Bill" OR so.STATUS = "Draft") '''
								+ where +
							'''
							GROUP BY
								soi.parent
					''', where_filter, as_dict=1)
	data = get_print_date(query)
	return columns, data

def get_print_date(data):
	for row in data:
		if row.STATUS != 'Draft':
			query = frappe.db.sql('''SELECT 
										pl.print_date_time 
									FROM 
										`tabPick List Item` pli
									LEFT JOIN
										`tabPick List` pl ON pl.name = pli.parent
									WHERE pl.docstatus  = 1 AND pli.sales_order = %(sales_order)s
									LIMIT 1''', {"sales_order": row.sales_order}, as_dict=1)
			if query:
				row.update({"pick_list_print": query[0].print_date_time})
	return data
								

