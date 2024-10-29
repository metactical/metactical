# Copyright (c) 2024, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
def execute(filters=None):
	columns = get_columns()
	conditions = get_conditions(filters)
	data = get_data(conditions, filters)

	return columns, data

def get_conditions(filters):
	conditions = ""
	limit = filters.get("limit")
	if filters.get('warehouse'):
		conditions += " and warehouse = %(warehouse)s"
	if filters.get('ifw_retailskusuffix'):
		conditions += " and ifw_retailskusuffix = %(ifw_retailskusuffix)s"
	if filters.get('item_code'):
		conditions += " and `tabItem`.item_code = %(item_code)s"
	if limit != "All":
		conditions += " limit {}".format(str(limit))

	return conditions

def get_data(conditions, filters):
	bin = frappe.db.sql("""
		SELECT
			`tabBin`.item_code, 
			ifw_retailskusuffix AS retail_sku, 
			`tabBin`.warehouse, 
			actual_qty-reserved_qty AS available_qty, 
			variant_of
		FROM
			`tabBin`
		JOIN 
			`tabItem` ON `tabBin`.item_code = `tabItem`.name
		WHERE 1 = 1 and has_variants=0 %s
	"""%(conditions), filters, as_dict=1)

	return bin

def get_columns():
	return [
		{
			"label": "Item Code",
			"fieldname": "item_code",
			"fieldtype": "Link",
			"options": "Item",
			"width": 150
		},
		{
			"label": "Retail SKU",
			"fieldname": "retail_sku",
			"fieldtype": "Data",
			"width": 150
		},
		{
			"label": "Variant Of",
			"fieldname": "variant_of",
			"fieldtype": "Link",
			"options": "Item",
			"width": 150
		},
		{
			"label": "Warehouse",
			"fieldname": "warehouse",
			"fieldtype": "Link",
			"options": "Warehouse",
			"width": 150
		},
		{
			"label": "Available Qty",
			"fieldname": "available_qty",
			"fieldtype": "Data",
			"width": 150
		}
	]

