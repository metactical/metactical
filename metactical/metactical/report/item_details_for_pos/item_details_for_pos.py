# Copyright (c) 2025, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe


def execute(filters=None):
	columns = get_columns()
	data = get_data(filters)
 
	return columns, data

def get_data(filters):
	pos_profile = filters.get("pos_profile")	
	pos_profile = frappe.db.get_value("POS Profile", pos_profile, ["ifw_default_lead_source", "selling_price_list", "name", "warehouse"], as_dict=True)
	price_list = pos_profile.selling_price_list
	warehouse = pos_profile.warehouse

	items = frappe.db.sql(f"""
		SELECT
			`tabItem`.item_code, 
			(SELECT actual_qty-reserved_qty from `tabBin` where item_code = `tabItem`.item_code and warehouse = '{warehouse}') as quantity ,
			`tabItem Price`.price_list_rate as rate,
			`tabItem`.item_name, tabItem.image,
			`tabItem`.brand, `tabItem`.ifw_retailskusuffix as retail_sku,
			`tabItem`.is_stock_item
		FROM
			`tabItem`
		Left JOIN
			`tabBin` ON `tabItem`.item_code = `tabBin`.item_code
		LEFT JOIN
			`tabItem Price` ON `tabItem Price`.item_code = `tabItem`.item_code
		WHERE
			`tabItem Price`.price_list = "{price_list}" and
			`tabItem`.disabled = 0 and
			`tabItem`.has_variants = 0
		Group BY
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
				AND (`tabPricing Rule`.for_price_list = '{price_list}' or `tabPricing Rule`.for_price_list is NULL)
				AND `tabPricing Rule`.disable = 0
				AND `tabPricing Rule`.valid_upto >= CURDATE()
			ORDER BY
				CAST(`tabPricing Rule`.priority AS UNSIGNED) DESC
			LIMIT 1;
		""", as_dict=1)


		if pricing_rule:
			item.discount_start_date = pricing_rule[0].discount_start_date
			item.discount_expiry_date = pricing_rule[0].discount_expiry_date
			item.on_sale = not pricing_rule[0].on_sale
			item.discount_price = item.rate - (item.rate * pricing_rule[0].discount_percentage / 100)
		
		data.append({
			"branch": pos_profile.name,
			"product": item.item_code,
			"quantity": item.quantity,
			"price": item.rate,
			"image": item.image,
			"retail_sku": item.retail_sku,
			"discount_expiry_date": item.discount_expiry_date,
			"discount_price": item.discount_price,
			"discount_start_date": item.discount_start_date,
			"on_sale": True if item.on_sale else False,
			"barcodes": ", ".join([b.barcode for b in frappe.db.get_all("Item Barcode", {"parent": item.item_code}, "barcode")]),
			"item_name": item.item_name,
			"brand": item.brand,
			"is_stock_item": item.is_stock_item
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
			"fieldtype": "Link",
			"options": "Item",
			"width": 150
		},
		{
			"label": "Retail Sku",
			"fieldname": "retail_sku",
			"fieldtype": "Data",
			"width": 150
		},
		{
			"label": "Image",
			"fieldname": "image",
			"fieldtype": "Data",
			"width": 150,
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
			"default": 0,
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
		},
		{
			"label": "Is Stock Item",
			"fieldname": "is_stock_item",
			"fieldtype": "Data",
			"width": 150
		}
	]
