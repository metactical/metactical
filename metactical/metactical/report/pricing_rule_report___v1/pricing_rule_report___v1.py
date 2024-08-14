# Copyright (c) 2024, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
def execute(filters=None):
	columns = get_columns(filters)
	conditions = get_conditions(filters)
	data = get_data(filters,  conditions)

	return columns, data

def get_conditions(filters):
	conditions = []
	
	if filters.get("apply_on") == "Item Code":
		conditions.append(f"apply_on = '{filters.get('apply_on')}'")

		item_codes = filters.get("item_code")
		if item_codes:
			# change the list of item_codes to tuple
			group_items = str(tuple(item_codes)).replace(",)", ")") if len(item_codes) == 1 else tuple(item_codes)
			conditions.append(f"price_item.item_code IN {group_items}")

	elif filters.get("apply_on") == "Item Group":
		conditions.append(f"apply_on = '{filters.get('apply_on')}'")

		item_group = filters.get("item_group")
		if item_group:
			# change the list of item_groups to tuple
			group_items = str(tuple(item_group)).replace(",)", ")") if len(group_items) == 1 else tuple(item_group)
			conditions.append(f"price_item.item_group IN {group_items}")
	
	elif filters.get("apply_on") == "Brand":
		conditions.append(f"apply_on = '{filters.get('apply_on')}'")

		brand = filters.get("brand")
		if brand:
			# change the list of brands to tuple
			group_items = str(tuple(brand)).replace(",)", ")") if len(brand) == 1 else tuple(brand)
			conditions.append(f"price_item.brand IN {group_items}")
		
	return conditions

def get_data(filters, conditions):
	conditions = " AND ".join(conditions)
	apply_on = filters.apply_on
	main_field = ""

	if apply_on == "Item Code":
		main_field = "item_code"
	elif apply_on == "Item Group":
		main_field = "item_group"
	elif apply_on == "Brand":
		main_field = "brand"

	pricing_rules = frappe.db.sql(f"""
		SELECT
			price_item.{main_field} as item_code, discount_percentage, rate_or_discount, 
			for_price_list, valid_from, valid_upto, disable,
			`tabPricing Rule`.name,
			rate, discount_percentage
		FROM
			`tabPricing Rule`
		JOIN
			`tabPricing Rule {apply_on}` price_item
		ON
			price_item.parent = `tabPricing Rule`.name
		WHERE
			{conditions}
	""", as_dict=1)

	item_codes = [pricing_rule.item_code for pricing_rule in pricing_rules]
	for pricing_rule in pricing_rules:
		if filters.get("apply_on") == "Item Code":
			item_names = frappe.db.get_all("Item", filters={"name": ["in", item_codes]}, fields=["name", "item_name", "ifw_retailskusuffix"])
			item_names = {item.name: item for item in item_names}

			pricing_rule.erp_sku = pricing_rule.item_code
			pricing_rule.item_name = item_names.get(pricing_rule.item_code).item_name
			pricing_rule.retail_sku = item_names.get(pricing_rule.item_code).ifw_retailskusuffix
			pricing_rule.price_list_rate = frappe.db.get_value("Item Price", {"price_list": pricing_rule.for_price_list, "item_code": pricing_rule.item_code}, "price_list_rate")

			# calculate the amount after discount
			if pricing_rule.rate_or_discount == "Discount Percentage":
				if pricing_rule.price_list_rate:
					pricing_rule.after_discount = pricing_rule.price_list_rate - (pricing_rule.price_list_rate * pricing_rule.discount_percentage / 100)

			elif pricing_rule.rate_or_discount == "Rate":
				pricing_rule.after_discount = pricing_rule.rate
		else:
			pricing_rule.erp_sku = pricing_rule.item_code

		pricing_rule.enabled = not pricing_rule.disable
		pricing_rule.rate_or_discount = pricing_rule.rate_or_discount
		pricing_rule.discount = str(pricing_rule.discount_percentage) + "%" if pricing_rule.rate_or_discount == "Discount Percentage" else pricing_rule.rate

	return pricing_rules

def get_columns(filters):
	columns = [{
			"fieldname": "erp_sku",
			"fieldtype": "Data",
			"label": filters.get("apply_on"),
			"width": 120	
	}]

	if filters.get("apply_on") == "Item Code":
		columns.append(
		{
			"fieldname": "retail_sku",
			"fieldtype": "Data",
			"label": "Retail Sku",
			"width": 120
		})
		columns.append({
			"fieldname": "item_name",
			"fieldtype": "Data",
			"label": "Item Name",
			"width": 120
		})
		
	columns += [
		{
			"fieldname": "rate_or_discount",
			"fieldtype": "data",
			"label": "Rate or Discount",
			"width": 120
		},
		{
			"fieldname": "discount",
			"fieldtype": "Data",
			"label": "Discount",
			"width": 120
		},
		{
			"fieldname": "for_price_list",
			"fieldtype": "Data",
			"label": "Price List",
			"width": 120
		},
		{
			"fieldname": "price_list_rate",
			"fieldtype": "Currency",
			"label": "Price List Rate",
			"width": 120
		},
		{
			"fieldname": "after_discount",
			"fieldtype": "Currency",
			"label": "After Discount",
			"width": 120
		},
		{
			"fieldname": "valid_from",
			"fieldtype": "Date",
			"label": "Valid From",
			"width": 120
		},
		{
			"fieldname": "valid_upto",
			"fieldtype": "Date",
			"label": "Valid Upto",
			"width": 120
		},
		{
			"fieldname": "enabled",
			"fieldtype": "Check",
			"label": "Enabled",
			"width": 120
		}
	]

	return columns