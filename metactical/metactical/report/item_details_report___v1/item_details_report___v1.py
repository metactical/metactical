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
	suppliers = []
	limit = filters.get("limit")
	if filters.get('supplier'):
		suppliers = frappe.parse_json(filters.get("supplier"))
		conditions += " and supplier IN %(supplier)s"
	elif filters.get('item_code'):
		conditions += " and item_code = %(item_code)s"
	if limit != "All":
		conditions += " limit {}".format(str(limit))

	return conditions

def get_data(conditions, filters):
	data = frappe.db.sql("""
		SELECT
			item_code, description, variant_of, brand, supplier, supplier_part_no, default_price_list
		FROM
			`tabItem`
		LEFT JOIN
			`tabItem Supplier` ON `tabItem`.name = `tabItem Supplier`.parent
		LEFT JOIN
			`tabSupplier` ON `tabItem Supplier`.supplier = `tabSupplier`.name
		WHERE 1 = 1 %s
	"""%(conditions), filters, as_dict=1)

	for d in data:
		d["default_supplier_cost_price"] = frappe.db.get_value("Item Price", {"item_code": d["item_code"], "price_list": d["default_price_list"]}, "price_list_rate")
		d["standard_selling_price"] = frappe.db.get_value("Item Price", {"item_code": d["item_code"], "price_list": "RET - Camo"}, "price_list_rate")

	return data

def get_columns():
	# Item_code	Item_description	Item_Template	Item_Brand	Supplier_Code	Supplier_Name	Default Supplier Cost Price	Standard Selling Price
	return [
		{
			"label": "Item Code",
			"fieldname": "item_code",
			"fieldtype": "Link",
			"options": "Item",
			"width": 150
		},
		{
			"label": "Item Description",
			"fieldname": "description",
			"fieldtype": "Data",
			"width": 150
		},
		{
			"label": "Item Template",
			"fieldname": "variant_of",
			"fieldtype": "Data",
			"width": 150
		},
		{
			"label": "Item Brand",
			"fieldname": "item_brand",
			"fieldtype": "Data",
			"width": 150
		},
		{
			"label": "Supplier Part No",
			"fieldname": "supplier_part_no",
			"fieldtype": "Data",
			"width": 150
		},
		{
			"label": "Supplier Name",
			"fieldname": "supplier",
			"fieldtype": "Data",
			"width": 150
		},
		{
			"label": "Default Supplier Cost Price",
			"fieldname": "default_supplier_cost_price",
			"fieldtype": "Currency",
			"width": 150
		},
		{
			"label": "Standard Selling Price",
			"fieldname": "standard_selling_price",
			"fieldtype": "Currency",
			"width": 150
		}
	]
