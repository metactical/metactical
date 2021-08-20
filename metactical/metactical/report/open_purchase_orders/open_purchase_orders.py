# Copyright (c) 2013, Techlift Technologies and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.utils import flt
from functools import reduce


def execute(filters=None):
	if not filters:
		filters = {}

	columns = get_column()
	data=[]

	item_orders = get_data(filters)
	for d in item_orders:
		row = {}
		row['po_date'] = d.transaction_date
		row['name'] = d.name
		row['item_code'] = d.item_code
		row['ifw_retailskusuffix'] = d.ifw_retailskusuffix
		row['item_name'] = d.item_name
		row['qty'] = d.qty
		row['current_qty'] = get_total_qoh(d.item_code)
		row['eta_date'] = d.eta_date
	

		data.append(row)

	return columns, data


def get_column():
	return [
		{
			"fieldname":"po_date",
			"label": "PO Date",
			"fieldtype": "Date",
			'width': 120
		},
		{
			"fieldname":"name",
			"label": "PO Number",
			"fieldtype": "Link",
			"options": "Purchase Order",
			'width': 120
		},
		{
			"fieldname":"item_code",
			"label": "Erp Sku",
			"fieldtype": "Link",
			"options": "Item",
			'width': 200
		},
		{
			"fieldname":"ifw_retailskusuffix",
			"label": "Retail SkuSuffix",
			"fieldtype": "Data",
			'width': 200
		},
		{
			"fieldname":"item_name",
			"label": "Item Name",
			"fieldtype": "Data",
			'width': 200
		},
		{
			"fieldname":"qty",
			"label": "Qty on Order",
			"fieldtype": "Float",
			"width": 120,
		},
		
		{
			"fieldname":"current_qty",
			"label": "TQOH (Total of all locations)",
			"fieldtype": "Float",
			"width": 120,
		},
		{
			"fieldname":"eta_date",
			"label": "ETA Date",
			"fieldtype": "Date",
			'width': 120
		},
	
	]


def get_data(filters):
	where_filter = {"from_date": filters.from_date, "to_date": filters.to_date}
	where = ""

	data = frappe.db.sql("""select c.item_code, c.item_name, c.qty,
		c.ifw_retailskusuffix,		
		p.name, p.transaction_date, p.eta_date, p.status
		from `tabPurchase Order Item` c inner join `tabPurchase Order` p on p.name = c.parent
		where 
			p.docstatus = 1 and (p.status = "To Receive" or p.status = "To Receive and Bill" )
			and p.transaction_date BETWEEN %(from_date)s AND %(to_date)s
		order by p.transaction_date
		"""+ where, where_filter, as_dict=1)
	return data


def get_total_qoh(item):
	bins = frappe.get_all("Bin", fields=['actual_qty'],
		filters=[
			["item_code", "=", item]
		])
	actual_qty = reduce(lambda x,y:x+y, map(lambda b:b["actual_qty"], bins), 0)

	return actual_qty
