# Copyright (c) 2013, Techlift Technologies and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	if not filters:
		filters = {}

	columns = get_column()
	data=[]

	item_sales = get_data(filters)
	for d in item_sales:
		row = {}
		row['sr_date'] = d.posting_date
		row['warehouse'] = d.warehouse
		row['ifw_retailskusuffix'] = d.ifw_retailskusuffix
		row['item_name'] = d.item_name
		row['qty'] = d.qty
		row['current_qty'] = d.current_qty
		row['quantity_difference'] = flt(d.quantity_difference)
		row['amount_difference'] = d.amount_difference
		row['owner'] = d.owner
		row['ifw_location'] = d.ifw_location

		data.append(row)

	return columns, data


def get_column():
	return [
		{
			"fieldname":"warehouse",
			"label": "Warehouse",
			"fieldtype": "Link",
			"options": "Warehouse",
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
			"fieldname":"current_qty",
			"label": "QOHSH (Before Adjustment)",
			"fieldtype": "Float",
			"width": 120,
		},
		{
			"fieldname":"quantity_difference",
			"label": "QTYADJ (Qty Diff)",
			"fieldtype": "Float",
			"width": 120,
		},
		{
			"fieldname":"qty",
			"label": "QOHActual (After Adjustment)",
			"fieldtype": "Float",
			"width": 120,
		},
		{
			"fieldname":"amount_difference",
			"label": "Adjustment Amount",
			"fieldtype": "Currency",
			"width": 120,
		},
		{
			"fieldname":"owner",
			"label": "Adjusted By",
			"fieldtype": "Link",
			"options": "User",
			'width': 200
		},
	
	]


def get_data(filters):
	where_filter = {"from_date": filters.from_date, "to_date": filters.to_date}
	where = ""

	data = frappe.db.sql("""select c.item_code, c.item_name, c.qty, c.current_qty, c.quantity_difference,
		c.valuation_rate, c.amount_difference, c.warehouse, 
		i.ifw_retailskusuffix, i.ifw_location,
		p.name, p.posting_date, p.owner
		from `tabStock Reconciliation Item` c inner join `tabStock Reconciliation` p on p.name = c.parent
		inner join `tabItem` i on c.item_code = i.name 
		where p.docstatus = 1 and p.posting_date BETWEEN %(from_date)s AND %(to_date)s
		order by p.posting_date
		"""+ where, where_filter, as_dict=1)
	return data
