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
			"width": 150
		},
		{
			"label": "Customer Purchase Order Number",
			"fieldname": "po_no",
			"fieldtype": "Data",
			"width": 150
		},
		{
			"label": "Date",
			"fieldname": "transaction_date",
			"fieldtype": "Date",
			"width": 150
		},
		{
			"label": "Pick List Printed",
			"fieldname": "pick_list_print",
			"fieldtype": "Datetime",
			"width": 150
		},
		{
			"label": "AvailableToShipFrom",
			"fieldname": "warehouse",
			"fieldtype": "Link",
			"options": "Warehouse",
			"width": 150
		},
		{
			"label": "Status",
			"fieldname": "STATUS",
			"fieldtype": "Data",
			"width": 150
		},
		{
			"label": "Tag",
			"fieldname": "tag",
			"fieldtype": "Data",
			"width": 150
		},
		{
			"label": "Source",
			"fieldname": "source",
			"fieldtype": "Link",
			"options": "Lead Source",
			"width": 150
		},
		{
			"label": "Customer",
			"fieldname": "customer",
			"fieldtype": "Link",
			"options": "Customer",
			"width": 150
		}
	]
	
	data = get_data(filters)
	return columns, data
	
def get_data(filters):
	data = []
	where = ''
	where_filter = {}
	
	if filters.get("from_date") and filters.get("to_date"):
		where = ' AND so.transaction_date BETWEEN %(from_date)s AND %(to_date)s '
		where_filter.update({'from_date': filters.get("from_date"), 'to_date': filters.get("to_date")})
		
	if filters.get("source"):
		where = ' AND so.source = %(source)s '
		where_filter.update({'source': filters.get("source")})
	
	query = frappe.db.sql('''
							SELECT
								so.name AS sales_order,
								so.po_no,
								so.transaction_date,
								so.STATUS,
								(select GROUP_CONCAT(tag SEPARATOR ', ') from `tabTag Link` tl where tl.parent = so.name) as tag,
								so.source,
								so.customer
							FROM
								`tabSales Order` so
							WHERE
								(so.STATUS = "To Deliver" OR so.STATUS = "To Deliver and Bill" OR so.STATUS = "Draft")'''
								+ where, where_filter, as_dict=1)
	init_data = get_print_date(query)
	warehouses = ['R01-Gor-Active Stock - ICL', 'R02-Edm-Active Stock - ICL', 'R03-Vic-Active Stock - ICL', 
					'R04-Mon-Active Stock - ICL', 'R05-DTN-Active Stock - ICL', 'R06-AMB-Active Stock',
					'R07-Queen-Active Stock - ICL', 'US01-ShipCalm-Active Stock - ICL', 'W01-WHS-Active Stock - ICL']
	for row in init_data:
		for warehouse in warehouses:
			is_available = check_availability(row.sales_order, warehouse)
			if is_available:
				row.update({"warehouse": warehouse})
				data.append(row.copy())
	return data
	
def check_availability(sales_order, warehouse):
	items = frappe.db.sql('''
							SELECT 
								item_code, qty 
							FROM 
								`tabSales Order Item` soi 
							WHERE soi.parent=%(sales_order)s''', {'sales_order': sales_order}, as_dict=1)
	for item in items:
		bin_qty = frappe.db.get_value('Bin', {'warehouse': warehouse, 'item_code': item.item_code}, 'actual_qty')
		if bin_qty is None:
			return False
		elif bin_qty < item.qty:
			return False
	return True

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
								

