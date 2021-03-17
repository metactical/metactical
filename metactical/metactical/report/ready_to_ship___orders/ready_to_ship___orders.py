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
			"label": "Warehouse",
			"fieldname": "warehouse",
			"fieldtype": "Link",
			"options": "Warehouse"
		},
		{
			"label": "Date",
			"fieldname": "transaction_date",
			"fieldtype": "Date"
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
			"label": "SE Reference",
			"fieldname": "ifw_old_reference",
			"fieldtype": "Data"
		},
		{
			"label": "Customer",
			"fieldname": "customer",
			"fieldtype": "Link",
			"options": "Customer",
		},
		{
			"label": "Ordered Qty",
			"fieldname": "qty",
			"fieldtype": "Float"
		},
		{
			"label": "Delivered Qty",
			"fieldname": "delivered_qty",
			"fieldtype": "Float"
		},
		{
			"label": "Qty To Deliver",
			"fieldname": "qty_to_deliver",
			"fieldtype": "Float"
		},
		{
			"label": "Available Qty",
			"fieldname": "available_qty",
			"fieldtype": "Float"
		},
		{
			"label": "Available Qty From All Warehouses",
			"fieldname": "available_qty_from_all_warehouses",
			"fieldtype": "Float"
		},
		{
			"label": "Item",
			"fieldname": "item_code",
			"fieldtype": "Link",
			"options": "item"
		},
		{
			"label": "Retail SKU Suffix",
			"fieldname": "ifw_retailskusuffix",
			"fieldtype": "Data"
		},
		{
			"label": "IFW Location",
			"fieldname": "ifw_location",
			"fieldtype": "Data"
		},
		{
			"label": "Rate",
			"fieldname": "rate",
			"fieldtype": "Float"
		},
		{
			"label": "Amount",
			"fieldname": "amount",
			"fieldtype": "float"
		},
		{
			"label": "Item Delivery Date",
			"fieldname": "delivery_date",
			"fieldtype": "Date"
		},
		{
			"label": "Item Name",
			"fieldname": "item_name",
			"fieldtype": "Data"
		},
		{
			"label": "Description",
			"fieldname": "description",
			"fieldtype": "Data"
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
	
	data = frappe.db.sql('''
							SELECT
								T.parent AS sales_order,
								T.po_no,
								T.ifw_old_reference AS " SE Reference",
								T.STATUS,
								T.customer,
								T.customer_name,
								T.source,
								T.transaction_date,
								T.tag,
								soi1.item_code,
								soi1.qty,
								soi1.delivered_qty,
								( soi1.qty - soi1.delivered_qty ) AS qty_to_deliver,
								( bin1.actual_qty - bin1.reserved_qty ) AS available_qty,
								( SELECT sum( actual_qty ) - sum( reserved_qty ) FROM `tabBin` WHERE item_code = soi1.item_code ) AS available_qty_from_all_warehouses,
								T.warehouse,
								soi1.ifw_retailskusuffix,
								soi1.ifw_location,
								soi1.rate,
								soi1.amount,
								soi1.delivery_date,
								soi1.item_name,
								soi1.description 
							FROM
								(
								SELECT
									so.STATUS,
									so.customer,
									so.source,
									so.po_no,
									so.ifw_old_reference,
									so.customer_name,
									so.transaction_date,
									soi.parent,
									bin.warehouse,
									(select GROUP_CONCAT(tag SEPARATOR ', ') from `tabTag Link` tl where tl.parent = soi.parent) as tag
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
									soi.parent,
									bin.warehouse
								HAVING
									count( soi.parent ) = ( SELECT count( * ) FROM `tabSales Order Item` WHERE parent = soi.parent ) 
								) AS T
								LEFT JOIN `tabSales Order Item` soi1 ON soi1.parent = T.parent
								LEFT JOIN `tabBin` bin1 ON bin1.item_code = soi1.item_code 
							WHERE
								bin1.warehouse = T.warehouse;
					''', where_filter, as_dict=1)
	return columns, data
