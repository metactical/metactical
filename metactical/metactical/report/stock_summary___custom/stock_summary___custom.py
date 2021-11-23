# Copyright (c) 2013, Techlift Technologies and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe import _

def execute(filters=None):
	columns, data = [], []
	columns = get_columns(filters)
	data = get_masters(filters)
	
	warehouse = filters.get("warehouse")
	if warehouse and "InTransit" in warehouse:
		data = get_transport_data(data, filters)
	
	return columns, data
	
def get_transport_data(data, filters):
	warehouse = filters.get("warehouse")
	for row in data:
		query = frappe.db.sql("""
								SELECT
									ste.sal_trackinginfo AS tracking_info,
									ste.sal_warehouseshipdate AS warehouse_ship_date
								FROM
									`tabStock Entry` AS ste
								LEFT JOIN
									`tabStock Entry Detail` AS item ON item.parent = ste.name
								WHERE
									item.item_code = %(item)s AND ste.to_warehouse = %(warehouse)s AND ste.stock_entry_type = 'Material Transfer'
								ORDER BY posting_date DESC LIMIT 1""", {"warehouse": warehouse, "item": row.erp_sku}, as_dict=1)
		if query[0]:
			row.update(
				{
					"tracking_info": query[0].tracking_info,
					"warehouse_ship_date": query[0].warehouse_ship_date.strftime("%d-%b-%Y") if query[0].warehouse_ship_date else None
				})
	return data
	
def get_masters(filters):
	warehouse = filters.get('warehouse')
	retail_sku = filters.get('retail_sku')
	
	extra_sql = ''
	where_dict = {"warehouse": warehouse}
	if retail_sku:
		extra_sql = " AND item.ifw_retailskusuffix LIKE %(retail_sku)s"
		where_dict.update({
			"retail_sku": '%{}%'.format(retail_sku)
		})
		
	if warehouse:
		data = frappe.db.sql("""SELECT 
									bin.item_code AS erp_sku,
									item.ifw_retailskusuffix AS retail_sku,
									item.item_name,
									bin.reserved_qty,
									bin.actual_qty
								FROM
									`tabBin` AS bin
								LEFT JOIN
									`tabItem` AS item ON item.name = bin.item_code
								WHERE
									bin.warehouse = %(warehouse)s AND (bin.actual_qty > 0 OR bin.reserved_qty > 0)
									{}
								""".format(extra_sql), where_dict, as_dict=1)
		return data
	
def get_columns(filters):
	columns = [
		{
			"fieldtype": "Link",
			"fieldname": "erp_sku",
			"label": _("ERP SKU"),
			"options": "Item",
			"width": 150
		},
		{
			"fieldtype": "Data",
			"fieldname": "retail_sku",
			"label": _("Retail SKU Suffix"),
			"width": 150
		},
		{
			"fieldtype": "Data",
			"fieldname": "item_name",
			"label": _("Item Name"),
			"width": 200
		},
		{
			"fieldtype": "Float",
			"fieldname": "reserved_qty",
			"label": _("Reserved Qty"),
			"width": 100
		},
		{
			"fieldtype": "Float",
			"fieldname": "actual_qty",
			"label": _("Actual Qty"),
			"width": 100
		}
	]
	
	warehouse = filters.get('warehouse')
	if warehouse and 'InTransit' in warehouse:
		extra_columns = [
			{
				"fieldtype": "Data",
				"fieldname": "tracking_info",
				"label": _("Tracking Info"),
				"width": 200
			},
			{
				"fieldtype": "Data",
				"fieldname": "warehouse_ship_date",
				"label": _("Warehouse Ship date"),
				"width": 150
			}
		]
		columns.extend(extra_columns)
	return columns
