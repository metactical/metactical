# Copyright (c) 2022, Techlift Technologies and contributors
# For license information, please see license.txt

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
		row['sre'] = d.name
		row['warehouse'] = d.warehouse
		row['ifw_retailskusuffix'] = d.ifw_retailskusuffix
		row['item_name'] = d.item_name	
		row['current_qty'] = d.current_qty
		row['quantity_difference'] = flt(d.quantity_difference)
		row['qty'] = d.qty
		row['amount_difference'] = d.amount_difference
		row['owner'] = d.owner
		

		data.append(row)

	return columns, data


def get_column():
	return [
		{
			"fieldname":"sre",
			"label": "Stock Reconciliation No",
			"fieldtype": "Link",
			"options": "Stock Reconciliation",
			'width': 200
		},
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

	data = frappe.db.sql("""select c.item_code, c.qty, c.current_qty, c.quantity_difference,
		c.valuation_rate, c.amount_difference, c.warehouse, 
		i.ifw_retailskusuffix, i.ifw_location, i.item_name,
		p.name, p.posting_date, p.owner
		from `tabStock Reconciliation Item` c 
		inner join `tabStock Reconciliation` p on p.name = c.parent
		inner join `tabItem` i on c.item_code = i.name 
		where c.quantity_difference < 0 and p.docstatus = 1 and p.posting_date BETWEEN %(from_date)s AND %(to_date)s
		order by c.warehouse
		"""+ where, where_filter, as_dict=1)
	return data
