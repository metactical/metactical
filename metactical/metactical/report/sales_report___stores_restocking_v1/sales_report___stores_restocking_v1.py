# Copyright (c) 2023, Metactical and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.utils import now 
from datetime import datetime

def execute(filters=None):
	if not filters:
		filters = {}
	
	columns = get_column()
	data = get_data(filters)

	return columns, data

def get_data(filters):
	data=[]

	opening_closing = get_report_data(filters)
	transit_warehouse = get_transit_warehouse(filters.get("warehouse"))

	for d in opening_closing:
		row = {}
		row['ifw_retailskusuffix'] = d.ifw_retailskusuffix
		row['item_code'] = d.item_code
		row['ifw_location'] = d.ifw_location
		row['item_name'] = d.item_name
		row['supplier_part_number'] = frappe.db.get_value("Item Supplier", {"parent": d.item_code}, "supplier_part_no")
		row['closing'] = d.actual_qty - d.reserved_qty
		wh_bin = frappe.db.get_value("Bin", {"warehouse": "W01-WHS-Active Stock - ICL", "item_code": d.item_code}, ["actual_qty", "reserved_qty"], as_dict=True)
		row['stock_levels'] = wh_bin.actual_qty - wh_bin.reserved_qty if wh_bin else 0
		row["in_transit"] = frappe.db.get_value("Bin", {"warehouse": transit_warehouse, "item_code": d.item_code}, "actual_qty") or 0
		row["button"] = '<button onClick="create_material_request(\'{}\')">Create Material Request</button>'.format(
							filters.get("warehouse", ""))
		row['preorder_level'] = d.warehouse_reorder_level
		row['preorder_qty'] = d.warehouse_reorder_qty
		months_to_block_order = frappe.db.get_all("Months List", filters={"parent": row['item_code']}, pluck="month")
		if months_to_block_order:
			current_month = datetime.now().strftime("%B")
			if current_month in months_to_block_order:
				continue
  
		if row['closing'] <= row['preorder_level'] and row['preorder_qty'] > 0 and row['stock_levels'] >= row['preorder_qty']:
			data.append(row)
   
	return data

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
			"fieldname":"preorder_level",
			"label": "Re-order Level",
			"width": 120,
			"fieldtype": "Int",
		},
		{
			"fieldname":"preorder_qty",
			"label": "Re-order Qty",
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

def get_report_data(filters):
	warehouse = filters.get("warehouse")
	data = frappe.db.sql(f"""
		select warehouse_reorder_qty, warehouse_reorder_level, i.item_code, i.item_name, i.ifw_retailskusuffix, i.ifw_location, b.warehouse,
			actual_qty, reserved_qty
		from `tabBin` b
		inner join `tabItem` i on b.item_code = i.item_code
		inner join `tabItem Reorder` ir on i.item_code = ir.parent
		where b.warehouse = '{warehouse}' 
  		and warehouse_reorder_level > 0 
    	and warehouse_reorder_qty > 0
		and material_request_type = 'Transfer'
		and ir.warehouse = '{warehouse}'
	""", as_dict=True) 
	
	# Sort data by location
	rows_with_none_location = []
	digit_rows_with_location = []
	non_digit_rows_with_location = []

	for row in data:
		if row['ifw_location'] is None:
			rows_with_none_location.append(row)
		else:
			if row['ifw_location'].split("-")[0].isdigit():
				digit_rows_with_location.append(row)
			else:
				non_digit_rows_with_location.append(row)
	print(data)
	data = []

	if digit_rows_with_location:
		def safe_location_sort(x):
			parts = x['ifw_location'].split("-")
			
			# Handle first segment (numeric part)
			first_segment = int(parts[0]) if parts and parts[0].isdigit() else 0
			
			# Handle second segment (safely get if exists)
			second_segment = parts[1] if len(parts) > 1 else ""
			
			# Handle third segment (safely get if exists)
			# Split by common separators in case the format is different
			if len(parts) > 1:
				# Check if second segment contains additional separators
				second_part = parts[1]
				sub_parts = second_part.split("|") if "|" in second_part else second_part.split()
				third_segment = sub_parts[1] if len(sub_parts) > 1 else ""
			else:
				third_segment = ""
				
			return (first_segment, second_segment, third_segment)
			
		# Sort using the safe sorting function
		data += sorted(digit_rows_with_location, key=safe_location_sort)
		
	if non_digit_rows_with_location:
		data += sorted(non_digit_rows_with_location, key=lambda x: x['ifw_location'])

	if rows_with_none_location:
		data += rows_with_none_location

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
	if list_type == "Buying": cond= " and buying = 1 and price_list like 'SUP%'"
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
def create_material_request(**args):
	args = frappe._dict(args)
	filters = {}
	if args.warehouse != "":
		filters["warehouse"] = args.warehouse
  
	init_data = get_data(filters)
	source_warehouse = "W01-WHS-Active Stock - ICL"
	transit_warehouse = get_transit_warehouse(filters.get("warehouse"))
	
	doc = frappe.new_doc("Material Request")
	doc.update({
		"material_request_type": "Material Transfer",
		"schedule_date": now(),
		"set_from_warehouse": source_warehouse,
		"set_warehouse": transit_warehouse
	})

	if not transit_warehouse:
		frappe.throw(_("The selected warehouse does not have a transit warehouse."))
  
	for row in init_data:
		qty = row["preorder_qty"] - row["in_transit"]	
  
		if qty > 0 and row["stock_levels"] >= qty:
			doc.append("items", {
				"from_warehouse": source_warehouse,
				"warehouse": transit_warehouse,
				"item_code": row["item_code"],
				"qty": qty,
				"ifw_location": row["ifw_location"]
			})
		elif qty > 0 and row["stock_levels"] < qty:
			frappe.msgprint(_("Not enough stock levels in warehouse {0} for item {1}. Available: {2}, Required: {3}").format(source_warehouse, row["item_code"], row["stock_levels"], qty))
   
	doc.insert(ignore_permissions=True)
	return doc