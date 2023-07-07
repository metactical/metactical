# Copyright (c) 2023, Metactical and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.desk.reportview import build_match_conditions
from frappe.utils import flt, cint, getdate, now, date_diff 

def execute(filters=None):
	if not filters:
		filters = {}
	if filters.get('pos_profile'): 
		warehouse, company = frappe.db.get_value("POS Profile", filters.get("pos_profile"), ["warehouse", "company"])
	conditions = get_conditions(filters)
	columns = get_column()
	data=[]

	opening_closing = get_data(conditions, filters)
	for d in opening_closing:
		if d.qty > 0:
			transit_warehouse = get_transit_warehouse(d.warehouse)
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
			row["in_transit"] = frappe.db.get_value("Bin", {"warehouse": transit_warehouse, "item_code": d.item_code}, "actual_qty") or 0
			row['sale'] = d.qty
			row['pos_profile'] = d.pos_profile
			row["button"] = '<button onClick="create_material_transfer(\'{}\', \'{}\', \'{}\')">Create Material Transfer</button>'.format(
								filters.get("pos_profile", ""), filters.get("to_date"), filters.get("item_code", ""))
			if row['stock_levels'] > 0:
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
			"fieldtype": "Int",
			"width": 80,
		},
		{
			"fieldname":"closing",
			"label": "QTYLeft",
			"fieldtype": "Int",
			"width": 130,
		},
		{
			"fieldname":"stock_levels",
			"label": "WHSQty",
			"width": 120,
			"fieldtype": "Int",
		},
		{
			"fieldname":"ifw_location",
			"label": "WHSLocation",
			"fieldtype": "Data",
			"width": 120,
		},	
		{
			"fieldname":"in_transit",
			"label": "InTrstQty",
			"width": 120,
			"fieldtype": "Int",
		},
		{
			"fieldname":"pos_profile",
			"label": "POSProfile",
			"fieldtype": "Link",
			"options": "POS Profile",
			"width": 150,
		},
		{
			"fieldname":"button",
			"fieldtype": "Data",
			"width": 200,
		}
	]

def get_transit_warehouse(warehouse):
	#Get transit warehouse
	w_split = warehouse.split("-")
	w_length = len(w_split)
	transit_warehouse = ""
	if w_split[-2] and w_split[-2].strip() == "Active Stock":
		for w in w_split:
			if w.strip() == "Active Stock":
				break
			transit_warehouse += w + "-"
	if transit_warehouse != "":
		transit_warehouse += "InTransit Stock - " + w_split[-1].strip()
	return transit_warehouse

def get_data(conditions, filters):
	data = frappe.db.sql("""
		SELECT 
			c.item_code, c.item_name, i.ifw_retailskusuffix, i.ifw_location, c.warehouse, sum(c.qty) as qty,
			p.pos_profile, p.company, c.uom, c.stock_uom, c.conversion_factor
		FROM
			`tabSales Invoice Item` c 
		INNER JOIN
			`tabSales Invoice` p ON p.name = c.parent
		INNER JOIN 
			`tabItem` i ON c.item_code = i.name 
		WHERE 
			p.docstatus = 1 AND p.is_pos =1 AND p.posting_date = '{}' 
			AND i.ais_blockfrmstoresale <> 1 {}
		GROUP BY 
			c.item_code, p.pos_profile
		ORDER BY 
			c.item_name, p.pos_profile
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
	
@frappe.whitelist()
def create_material_transfer(**args):
	args = frappe._dict(args)
	filters = {}
	if args.pos_profile != "":
		filters["pos_profile"] = args.pos_profile
	if args.to_date != "":
		filters["to_date"] = args.to_date
	if args.item_code != "":
		filters["item_code"] = args.item_code
		
	conditions = get_conditions(filters)
	init_data = get_data(conditions, filters)
	source_warehouse = "W01-WHS-Active Stock - " + frappe.db.get_value("Company", init_data[0].company, "abbr")
	doc = frappe.new_doc("Stock Entry")
	doc.update({
		"stock_entry_type": "Material Transfer",
		"ais_from_report": 1
	})
	for row in init_data:
		wh_actual = frappe.db.get_value("Bin", {"warehouse": source_warehouse, "item_code": row.item_code}, "actual_qty") or 0.0
		wh_res = frappe.db.get_value("Bin", {"warehouse": source_warehouse, "item_code": row.item_code}, "reserved_qty") or 0.0
		stock_levels = wh_actual - wh_res
		transit_warehouse = get_transit_warehouse(row.warehouse)
		if stock_levels > 0 and transit_warehouse != "":
			doc.append("items", {
				"s_warehouse": source_warehouse,
				"t_warehouse": transit_warehouse,
				"item_code": row.item_code,
				"qty": row.qty,
				"uom": row.uom,
				"stock_uom": row.stock_uom,
				"conversion_factor": row.conversion_factor
			})
	doc.insert(ignore_permissions=True)
	return doc
