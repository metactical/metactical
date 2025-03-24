# Copyright (c) 2025, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe


def execute(filters=None):
	columns = get_columns()
	data = get_data(filters)
 
	return columns, data

def get_data(filters):
	pos_profile = frappe.db.get_value("POS Profile", filters.get("pos_profile"), ["ifw_default_lead_source", "selling_price_list", "name"], as_dict=True)
	price_list = pos_profile.selling_price_list
 
	if not pos_profile.ifw_default_lead_source:
		frappe.throw("Please set default lead source in POS Profile")
  
	if not pos_profile.selling_price_list:
		price_list = frappe.db.get_single_value("Stock Settings", "ais_default_price_list")
  
	if not price_list:
		frappe.throw("Please set default price list in Stock Settings or POS Profile")
  
	warehouses = frappe.db.get_all("SB Warehouse Inventory Sync", filters={"parent": pos_profile.ifw_default_lead_source}, fields=["warehouse"])
	if not warehouses:
		frappe.throw("No warehouses found for the selected in the <a href='/app/lead-source/{0}'>Lead Source</a>".format(pos_profile.ifw_default_lead_source))
 
	warehouses = [warehouse.warehouse for warehouse in warehouses]
	warehouses = tuple(warehouses) if len(warehouses) > 1 else f"('{warehouses[0]}')"
  
	if not warehouses:
		frappe.throw("No warehouses found for the selected in the Lead Source")
 
	items = frappe.db.sql(f"""
		SELECT
			`tabItem`.item_code, 
   			sum(tabBin.actual_qty - tabBin.reserved_qty) as quantity,
			`tabItem Price`.price_list_rate as rate,
			`tabItem`.item_name,
			`tabItem`.brand
		FROM
			`tabItem`
		JOIN
			`tabBin` ON `tabItem`.item_code = `tabBin`.item_code
		LEFT JOIN
			`tabItem Price` ON `tabItem Price`.item_code = `tabItem`.item_code
		WHERE
			tabBin.warehouse IN {warehouses} and 
			`tabItem Price`.price_list = "{price_list}" and
			`tabItem`.disabled = 0 and
			`tabItem`.has_variants = 0 and
			`tabItem`.is_stock_item = 1 and
			tabBin.actual_qty - tabBin.reserved_qty > 0
		Group by 
			`tabItem`.item_code
	""", as_dict=1)
 
 
	data = []
	
	for item in items:        
		# select all pricing rules for the item and pick the one with the highest priority for each item
		pricing_rule = frappe.db.sql(f"""
			SELECT
				valid_from AS discount_start_date,
				valid_upto AS discount_expiry_date,
				disable AS on_sale,
				discount_percentage
			FROM
				`tabPricing Rule Item Code`
			JOIN
				`tabPricing Rule` ON `tabPricing Rule`.name = `tabPricing Rule Item Code`.parent
			WHERE
				`tabPricing Rule Item Code`.item_code = '{item.item_code}'
				AND `tabPricing Rule`.for_price_list = '{price_list}'
				AND `tabPricing Rule`.disable = 0
				AND `tabPricing Rule Item Code`.parent IS NOT NULL
			ORDER BY
				`tabPricing Rule`.priority DESC,
				`tabPricing Rule`.modified Desc
			LIMIT 1;
		""", as_dict=1)
  
  
		if pricing_rule:
			item.discount_start_date = pricing_rule[0].discount_start_date
			item.discount_expiry_date = pricing_rule[0].discount_expiry_date
			item.on_sale = not pricing_rule[0].on_sale
			item.discount_price = item.rate - (item.rate * pricing_rule[0].discount_percentage / 100)
		
		barcodes = frappe.db.get_values("Item Barcode", {"parent": item.item_code}, "barcode")
		item.barcodes = ", ".join([barcode[0] for barcode in barcodes]) if barcodes else ""
  
		data.append({
			"branch": pos_profile.name,
			"product": item.item_code,
			"quantity": item.quantity,
			"price": item.rate,
			"discount_expiry_date": item.discount_expiry_date,
			"discount_price": item.discount_price,
			"discount_start_date": item.discount_start_date,
			"on_sale": True if item.on_sale else False,
			"barcodes": frappe.db.get_value("Item Barcode", {"parent": item.item_code}, "barcode"),
			"item_name": item.item_name,
			"brand": item.brand,
		})
  
	return data

def get_columns():
	return [
		{
			"label": "Branch",
			"fieldname": "branch",
			"fieldtype": "Data",
			"width": 150
		},
		{
			"label": "Sku",
			"fieldname": "product",
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
			"label": "Brand",
			"fieldname": "brand",
			"fieldtype": "Data",
			"width": 150
		},
		{
			"label": "Quantity",
			"fieldname": "quantity",
			"fieldtype": "Data",
			"width": 150
		},
		{
			"label": "Discount Expiry Date",
			"fieldname": "discount_expiry_date",
			"fieldtype": "Data",
			"width": 150
		},
		{
			"label": "Discount Price",
			"fieldname": "discount_price",
			"fieldtype": "Data",
			"width": 150
		},
		{
			"label": "Discount Start Date",
			"fieldname": "discount_start_date",
			"fieldtype": "Data",
			"width": 150
		},
		{
			"label": "On Sale",
			"fieldname": "on_sale",
			"fieldtype": "Data",
			"width": 150
		},
		{
			"label": "Price",
			"fieldname": "price",
			"fieldtype": "Data",
			"width": 150
		},
		{
			"label": "Barcodes",
			"fieldname": "barcodes",
			"fieldtype": "Data",
			"width": 150
		}
	]