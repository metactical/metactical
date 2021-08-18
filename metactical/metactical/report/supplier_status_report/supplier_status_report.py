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
		row['supplier_name'] = d.name
		row['supplier_country'] = d.country
		row['billing_currency'] = d.default_currency
		row['open_po'] = int(get_open_po(d.get("name")))
		row['open_pr'] = int(get_open_pr(d.get("name")))

		row['open_pi'] = get_open_pi(d.get("name"))

		data.append(row)

	return columns, data


def get_column():
	return [
		{
			"fieldname":"supplier_name",
			"label": "Supplier",
			"fieldtype": "Link",
			"options": "Supplier",
			'width': 200
		},
		{
			"fieldname":"supplier_country",
			"label": "Supplier Country",
			"fieldtype": "Data",
			'width': 120
		},
		{
			"fieldname":"billing_currency",
			"label": "Billing Curency",
			"fieldtype": "Data",
			'width': 120
		},
		{
			"fieldname":"open_po",
			"label": "No Open POrders ",
			"fieldtype": "Int",
			'width': 200
		},
		{
			"fieldname":"open_pr",
			"label": "No Open PReceipts ",
			"fieldtype": "Int",
			'width': 200
		},
		{
			"fieldname":"open_pi",
			"label": "No Open PInvoice ",
			"fieldtype": "Int",
			'width': 200
		},
			
	]


def get_data(filters):
	data = frappe.db.sql("""select ts.name, ts.country, ts.default_currency						
		from `tabSupplier` ts
		""", as_dict=1)
	return data


def get_open_po(supplier):
	qty = 0
	data = frappe.db.sql("""select COUNT(po.name)
		 
		from `tabPurchase Order` po 
		where 
			po.supplier = %s and	
			po.docstatus = 1 and
			(po.status = "To Receive" or po.status = "To Receive and Bill" 
			or po.status = "To Bill")
		""",(supplier), as_list=1)
	if data:
		qty = data[0][0] or 0
	return qty


def get_open_pr(supplier):
	
	data = frappe.db.sql("""select COUNT(pr.name)
		from `tabPurchase Receipt` pr
		where
			pr.supplier = %s and
			pr.docstatus = 1 and
			pr.status = "To Bill"
		""",(supplier), as_list=1)

	if data:
		qty = data[0][0] or 0
	return qty



def get_open_pi(supplier):

	data = frappe.db.sql("""select count(pi.name) as total_pi
		from `tabPurchase Invoice` pi
		where
			pi.supplier = %s and
			pi.docstatus = 1 and
			(pi.status != "Paid")
		""",(supplier))
	if data:
		qty = data[0][0] or 0
	return qty
