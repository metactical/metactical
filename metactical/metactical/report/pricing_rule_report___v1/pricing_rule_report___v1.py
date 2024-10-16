# Copyright (c) 2024, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.utils.xlsxutils import make_xlsx
from frappe import _
import json
from metactical.custom_scripts.utils.metactical_utils import export_query

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

	if filters.get("price_list"):
		conditions.append(f"for_price_list = '{filters.get('price_list')}'")
		
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
			for_price_list, valid_from, valid_upto, disable, priority,
			`tabPricing Rule`.name, 
			rate, discount_percentage, discount_amount
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
			pricing_rule.priority = pricing_rule.priority
			
			# calculate the amount after discount
			if pricing_rule.price_list_rate:
				if pricing_rule.rate_or_discount == "Discount Percentage":
					if pricing_rule.price_list_rate:
						pricing_rule.after_discount = pricing_rule.price_list_rate - (pricing_rule.price_list_rate * pricing_rule.discount_percentage / 100)

				elif pricing_rule.rate_or_discount == "Rate":
					pricing_rule.after_discount = pricing_rule.rate
				elif pricing_rule.rate_or_discount == "Discount Amount":
					pricing_rule.after_discount = pricing_rule.price_list_rate - pricing_rule.discount_amount
		else:
			pricing_rule.erp_sku = pricing_rule.item_code

		pricing_rule.enabled = not pricing_rule.disable
		pricing_rule.rate_or_discount = pricing_rule.rate_or_discount

		if pricing_rule.rate_or_discount == "Discount Percentage":
			pricing_rule.discount = str(pricing_rule.discount_percentage)
		elif pricing_rule.rate_or_discount == "Rate":
			pricing_rule.discount = pricing_rule.rate
		elif pricing_rule.rate_or_discount == "Discount Amount":
			pricing_rule.discount = pricing_rule.discount_amount

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
			"label": "Discount/Percentage",
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
		},
		{
			"fieldname": "priority",
			"fieldtype": "Int",
			"label": "Priority",
			"width": 120
		}
	]

	return columns
@frappe.whitelist()
def download(apply_on, item_group, brand, item_code, price_list):
	filters = frappe._dict({
		"apply_on": apply_on,
		"item_group": item_group,
		"brand": brand,
		"item_code": json.loads(item_code),
		"price_list": price_list
	})

	columns, data = execute(filters)

	columns_list = [col.get("label") for col in columns]  # Extract column labels in one line
	xlsx_data = [columns_list] + build_xlsx(data, columns)  # Insert headers and data in one step

	price_list = filters.get("price_list") or get_price_list(xlsx_data)

	xlsx_file = make_xlsx(convert_data(xlsx_data, price_list), "excel_data").getvalue()

	frappe.local.response.update({
		"filecontent": xlsx_file,
		"type": "binary",
		"filename": f"{filters.get('price_list')} - Pricing Rule Report.xlsx"
	})

def get_price_list(data):
	# Simplified to return the first valid price list found
	return next((row[5] for row in data[1:] if row[5]), "")

def build_xlsx(rows, columns):
	# Simplified using list comprehension
	return [[row.get(col.get("fieldname")) for col in columns] for row in rows]

def convert_data(data, price_list):
	headers = [
		'Retail SKU', 'Item Name', f'{price_list}', 'Rate or Percentage',
		f'{price_list} Discount Percentage', f'{price_list} - AfterDiscount',
		'Enabled', 'Valid FromDate', 'ValidToDate', 'Priority'
	]
	
	rows = [
		[
			row[1], row[2], row[6], row[3], row[4], row[7],
			row[10], row[8], row[9], row[11]
		] for row in data[1:]
	]
	
	return [headers] + rows
