# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.desk.reportview import build_match_conditions
from frappe.utils import flt, cint, getdate, now, date_diff 

def execute(filters=None):
	if not filters:
		filters = {}
	# filters["warehouse"] = frappe.db.get_value("POS Profile", filters.get("pos_profile"), "warehouse")
	conditions = get_conditions(filters)
	columns = get_column()
	data=[]

	opening_closing = get_data(conditions, filters)
	for d in opening_closing:
		row = {}
		row['ifw_retailskusuffix'] = d.ifw_retailskusuffix
		row['item_code'] = d.item_code
		row['ifw_location'] = d.ifw_location
		row['item_name'] = d.item_name
		row['supplier_part_number'] = frappe.db.get_value("Item Supplier", {"parent": d.item_code}, "supplier_part_no")
		row['closing'] = frappe.db.get_value("Bin", {"warehouse": d.warehouse, "item_code": d.item_code}, "actual_qty") or 0.0
		wh_actual = frappe.db.get_value("Bin", {"warehouse": "W01-WHS-Active Stock - ICL", "item_code": d.item_code}, "actual_qty") or 0.0
		wh_res = frappe.db.get_value("Bin", {"warehouse": "W01-WHS-Active Stock - ICL", "item_code": d.item_code}, "reserved_qty") or 0.0
		row['stock_levels'] = wh_actual - wh_res
		# row["stock_levels"] = d.warehouse_reorder_level or 0
		row['retail_price'] = get_item_details(d.item_code, "Selling")
		row['price_list_cost'] = get_item_details(d.item_code, "Buying")
		row['sale'] = d.qty
		row['pos_profile'] = d.pos_profile
		data.append(row)

	return columns, data


def get_column():
	return [
		{
			"fieldname":"ifw_retailskusuffix",
			"label": "RetailSkuSuffix",
			"width": 120,
			"fieldtype": "Data",
		},

		{
			"fieldname":"item_code",
			"label": "ERPItemNo.",
			"width": 120,
			"fieldtype": "Link",
			"options": "Item",
	
		},
		{
			"fieldname":"item_name",
			"label": "ItemName",
			"width": 100,
			"fieldtype": "Data",
			
		},


		{
			"fieldname":"supplier_part_number",
			"label": "SupplierSku",
			"width": 150,
			"fieldtype": "Data",
			
		},


		{
			"fieldname":"sale",
			"label": "QTYSold",
			"fieldtype": "Float",
			"width": 80,
		},

		{
			"fieldname":"closing",
			"label": "QTYLeft",
			"fieldtype": "Float",
			"width": 130,
		},

		{
			"fieldname":"stock_levels",
			"label": "WHSQty",
			"width": 120,
			"fieldtype": "Float",
		},

		{
			"fieldname":"ifw_location",
			"label": "WHSLocation",
			"fieldtype": "Data",
			"width": 120,
		},

		{
			"fieldname":"retail_price",
			"label": "Price",
			"fieldtype": "Currency",
			"width": 120,
		},


		{
			"fieldname":"price_list_cost",
			"label": "CST",
			"fieldtype": "Currency",
			"width": 130,
		},


		{
			"fieldname":"pos_profile",
			"label": "POSProfile",
			"fieldtype": "Link",
			"options": "POS Profile",
			"width": 150,
		},
	]



def get_data(conditions, filters):
	data = frappe.db.sql("""select c.item_code, c.item_name, i.ifw_retailskusuffix, i.ifw_location, c.warehouse, sum(c.qty) as qty,
		p.pos_profile
		from `tabSales Invoice Item` c inner join `tabSales Invoice` p on p.name = c.parent
		inner join `tabItem` i on c.item_code = i.name 
		where p.docstatus = 1 and is_pos =1 and p.posting_date = '{}' {}
		group by 1,7 order by 2,7
		""".format(filters.get("to_date"), conditions), as_dict=1)
	return data

def get_conditions(filters, sales_order=None):
	conditions = ""
	if filters.get("item_code"):
		conditions += " and c.item_code = '{}'".format(filters.get("item_code"))
	if filters.get("pos_profile"):
		conditions += " and p.pos_profile = '{}'".format(filters.get("pos_profile"))
	return conditions


@frappe.whitelist()
def get_item_details(item, list_type="Selling"):
	cond = " and selling = 1"
	if list_type == "Buying": cond= " and buying = 1"
	rate = 0
	date = frappe.utils.nowdate()
	r = frappe.db.sql("select price_list_rate from `tabItem Price` where '{}' between valid_from and valid_upto and item_code = '{}' {} limit 1".format(date, item, cond))
	if r:
		if r[0][0]:
			rate = r[0][0]
	else:
		r = frappe.db.sql("select price_list_rate from `tabItem Price` where (valid_from <= '{}' or valid_upto >= '{}') and item_code = '{}' {} limit 1".format(date, date, item, cond))
		if r:
			if r[0][0]:
				rate = r[0][0]
		else:
			r = frappe.db.sql("select price_list_rate from `tabItem Price` where valid_from IS NULL and valid_upto IS NULL and item_code = '{}' {} limit 1".format(item, cond))
			if r:
				if r[0][0]:
					rate = r[0][0]
	return rate