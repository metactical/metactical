# Copyright (c) 2025, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
def execute(filters=None):
    # return if location filter is set and length of the chosen location is less than 3
	if "location" in filters and not filters.get("retail_sku"):
		if len(filters.get("location")) < 3:
			print("Location filter is set and length of the chosen location is less than 2")
			return [], []
	elif not filters.get("location") and not filters.get("retail_sku"):
		return [], []

    
	columns = get_columns()
	conditions = get_conditions(filters)
 
	data = []
	if conditions:
		data = get_data(conditions)
 
	return columns, data

def get_conditions(filters):
	conditions = []
	
	if filters.get("retail_sku"):
		conditions.append(f"`tabItem`.ifw_retailskusuffix = {frappe.db.escape(filters.get('retail_sku'))}")
		
	if filters.get("location"):
		conditions.append(f"ifw_location like '%{filters.get('location')}%'")
  
	if filters.get("warehouse"):
		conditions.append(f"`tabBin`.warehouse = {frappe.db.escape(filters.get('warehouse'))}")
	
	filter = "WHERE " + " AND ".join(conditions) if conditions else ""
	return filter

def get_data(filters):    
    items = frappe.db.sql(f"""
		SELECT `tabItem`.item_code, 
  				ifw_retailskusuffix, 
      			item_name, 
         		ifw_location, 
				(actual_qty - reserved_qty) as qoh,
				`tabBin`.warehouse,
				(SELECT GROUP_CONCAT(barcode)
					FROM `tabItem Barcode`
					WHERE parent = `tabItem`.name
					GROUP BY parent) as barcode
		FROM `tabItem`
		LEFT JOIN `tabBin` ON `tabItem`.name = `tabBin`.item_code
		{filters}
		ORDER BY item_code
	""", as_dict=True)
    
    return items
    
def get_columns():
	return [
		{
			"label": "ERP Item Code",
			"fieldname": "item_code",
			"fieldtype": "Link",
			"options": "Item",
			"width": 150
		},
		{
			"label": "Retail SKU",
			"fieldname": "ifw_retailskusuffix",
			"fieldtype": "Data",
			"width": 150
		},
		{
			"label": "Item Name",
			"fieldname": "item_name",
			"fieldtype": "Data",
			"width": 150
		},
		{
			"label": "QoH",
			"fieldname": "qoh",
			"fieldtype": "Float",
			"width": 150
		},
		{
			"label": "Barcode",
			"fieldname": "barcode",
			"fieldtype": "Data",
			"width": 150
		},
		{
			"label": "Location",
			"fieldname": "ifw_location",
			"fieldtype": "Data",
			"width": 200
		},
		{
			"label": "Warehouse",
			"fieldname": "warehouse",
			"fieldtype": "Link",
			"options": "Warehouse",
			"width": 200
		}
	]