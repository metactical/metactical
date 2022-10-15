# Copyright (c) 2013, Techlift Technologies and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe import _
import datetime

def execute(filters=None):
	columns, data = [], []
	
	columns = get_columns()
	data = get_masters(filters)
	data = get_ste_details(data)
	return columns, data
	
def get_masters(filters):
	warehouse = filters.get('warehouse')
	if warehouse:
		data = frappe.db.sql("""
								SELECT
									bin.warehouse AS to_warehouse,
									item.ifw_retailskusuffix AS retail_sku,
									bin.item_code AS erp_sku,
									item.item_name,
									bin.reserved_qty,
									bin.actual_qty 
								FROM
									`tabBin` AS bin
								LEFT JOIN
									`tabItem` AS item ON item.name = bin.item_code
								WHERE
									bin.warehouse = %(warehouse)s AND (bin.reserved_qty > 0 or bin.actual_qty > 0)
							""", {"warehouse": warehouse}, as_dict=1)
		return data
		
def get_ste_details(data):
	result = []
	for row in data:
		warehouse = row['to_warehouse']
		item_code = row['erp_sku']
		remaining_qty = row['actual_qty'] + row['reserved_qty']
		limit = 0
		temp_result = []
		while remaining_qty > 0:
			limit = limit + 1
			query = frappe.db.sql("""
						SELECT
							ste.posting_date AS date,
							ste.name AS ste_number,
							user.full_name AS created_by,
							details.s_warehouse AS from_warehouse,
							details.qty,
							ste.sal_trackinginfo,
							ste.sal_warehouseshipdate
						FROM
							`tabStock Entry` AS ste
						LEFT JOIN 
							`tabStock Entry Detail` AS details ON details.parent = ste.name
						LEFT JOIN
							`tabUser` AS user ON user.name = ste.owner
						WHERE
							details.t_warehouse = %(warehouse)s AND details.item_code = %(item_code)s
							AND ste.docstatus = 1 AND 
							(SELECT name FROM `tabStock Entry` WHERE received_from_stock = ste.name OR
								outgoing_stock_entry = ste.name LIMIT 1) IS NULL
						GROUP BY
							ste.name, ste.posting_date, user.full_name, details.s_warehouse
						ORDER BY ste.posting_date DESC LIMIT %(limit)s
					""", {"warehouse": warehouse, "item_code": item_code, "limit": limit}, as_dict=1)
			#
			# If actual_qty + reserved_qty > ste.qty means there is more than one 
			# ste therefore run again with limit increased. When number of rows is
			# less than limit then it means some of the items were not received through
			# transfer i.e those received through Purchase Receipt
			#	
			if query:
				temp_result = query
				if len(query) == limit:
					remaining_qty = remaining_qty - query[limit-1].qty
				else:
					remaining_qty = 0
			else:
				result.append(row)
				remaining_qty = 0
		
		for res in temp_result:
			age = datetime.date.today() - res['date']
			res.update({
				"aging_days": age.days
			})
			result.append(dict(row, **res))
	return result
			
		
	
def get_columns():
	columns = [
		{
			"fieldname": "date",
			"fieldtype": "Date",
			"label": _("Date"),
			"width": 100
		},
		{
			"fieldname": "ste_number",
			"fieldtype": "Link",
			"label": _("STE Number"),
			"options": "Stock Entry",
			"width": 150
		},
		{
			"fieldname": "created_by",
			"fieldtype": "Data",
			"label": _("Created By"),
			"width": 150
		},
		{
			"fieldname": "from_warehouse",
			"fieldtype": "Link",
			"label": _("Warehouse From"),
			"options": "Warehouse",
			"width": 150
		},
		{
			"fieldname": "to_warehouse",
			"fieldtype": "Link",
			"label": _("Warehouse To"),
			"options": "Warehouse",
			"width": 150
		},
		{
			"fieldname": "retail_sku",
			"fieldtype": "Data",
			"label": _("Retail SKU"),
			"width": 150
		},
		{
			"fieldname": "erp_sku",
			"fieldtype": "Link",
			"label": _("ERP SKU"),
			"options": "Item",
			"width": 150
		},
		{
			"fieldname": "item_name",
			"fieldtype": "Data",
			"label": _("Item Name"),
			"width": 200
		},
		{
			"fieldname": "reserved_qty",
			"fieldtype": "Float",
			"label": _("Reserved Qty"),
			"width": 100
		}, 
		{
			"fieldname": "actual_qty",
			"fieldtype": "Float",
			"label": _("Actual Qty"),
			"width": 100
		},
		{
			"fieldname": "aging_days",
			"fieldtype": "Int",
			"label": _("Aging Days"),
			"width": 100
		},
		{
			"fieldname": "sal_warehouseshipdate",
			"fieldtype": "Date",
			"label": _("Warehouse Shipdate"),
			"width": 100
		},
		{
			"fieldname": "sal_trackinginfo",
			"fieldtype": "Data",
			"label": _("Tracking Info"),
			"width": 150
		}
	]
	return columns
