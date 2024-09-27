# Copyright (c) 2024, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe

def execute(filters=None):
	purchase_orders = filters.get("purchase_order") if filters.get("purchase_order") else None
	purchase_receipts = filters.get("purchase_receipt") if filters.get("purchase_receipt") else None
	supplier = filters.get("supplier") if filters.get("supplier") else None

	if not purchase_orders and not purchase_receipts and not supplier:
		return [], []

	columns = get_columns(purchase_orders, purchase_receipts, supplier)
	data = get_data(purchase_orders, purchase_receipts, supplier)
	return columns, data

def get_data(purchase_orders, purchase_receipts, supplier):
	doctype = ""
	if purchase_orders or purchase_receipts:
		doctype = "Purchase Order" if purchase_orders else "Purchase Receipt"
		docnames = purchase_orders if purchase_orders else purchase_receipts		

		items = frappe.db.sql(f""" SELECT doc.item_code, i.ifw_location, doc.parent as name, i.ifw_retailskusuffix as retail_sku
									FROM `tab{doctype} Item` doc
									JOIN `tabItem` i on doc.item_code = i.name
									WHERE doc.parent IN %s """, (docnames,), as_dict=True) 
	elif supplier:
		items = frappe.db.sql(""" SELECT item_code, ifw_location, supplier as name, ifw_retailskusuffix as retail_sku
									FROM `tabItem Supplier`
									JOIN `tabItem` on item_code = `tabItem Supplier`.parent
									WHERE supplier = %s """, supplier, as_dict=True)
	
	data = []
	for item in items:
		row = {
			"item_code": item["item_code"],
			"location": item["ifw_location"],
			"document": item["name"],
			"retail_sku": item["retail_sku"]
		}

		data.append(row)

	return data


def get_columns(purchase_orders, purchase_receipts, supplier):
	columns = []

	if purchase_orders:
		columns.append({
			"label": "Purchase Order",
			"fieldname": "document",
			"fieldtype": "Data",
			"width": 200
		})

	if purchase_receipts:
		columns.append({
			"label": "Purchase Receipt",
			"fieldname": "document",
			"fieldtype": "Data",
			"width": 200

		})
	
	if supplier:
		columns.append({
			"label": "Supplier",
			"fieldname": "document",
			"fieldtype": "Data",
			"width": 200
		})

	columns.append({
		"label": "ERP SKU",
		"fieldname": "item_code",
		"fieldtype": "Link",
		"options": "Item",
		"width": 200
	})

	columns.append({
		"label": "Retail SKU",
		"fieldname": "retail_sku",
		"fieldtype": "Data",
		"width": 200
	})

	columns.append({
		"label": "Location",
		"fieldname": "location",
		"fieldtype": "Data",
		"width": 250
	})

	return columns