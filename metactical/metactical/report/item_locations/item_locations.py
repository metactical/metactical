# Copyright (c) 2024, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe

def execute(filters=None):
	purchase_orders = filters.get("purchase_order") if filters.get("purchase_order") else None
	purchase_invoices = filters.get("purchase_invoice") if filters.get("purchase_invoice") else None

	if not purchase_orders and not purchase_invoices:
		return [], []

	columns = get_columns(purchase_orders, purchase_invoices)
	data = get_data(purchase_orders, purchase_invoices)
	return columns, data

def get_data(purchase_orders, purchase_invoices):
	doctype = "Purchase Order" if purchase_orders else "Purchase Invoice"
	docnames = purchase_orders if purchase_orders else purchase_invoices

	items = frappe.db.sql(f""" SELECT doc.item_code, i.ifw_location, doc.parent as name
								FROM `tab{doctype} Item` doc
								JOIN `tabItem` i on doc.item_code = i.name
								WHERE doc.parent IN %s """, (docnames,), as_dict=True) 
	
	data = []
	for item in items:
		row = {
			"item_code": item["item_code"],
			"location": item["ifw_location"],
			"document": item["name"]
		}

		data.append(row)

	return data


def get_columns(purchase_orders, purchase_invoices):
	columns = []

	if purchase_orders:
		columns.append({
			"label": "Purchase Order",
			"fieldname": "document",
			"fieldtype": "Data",
			"width": 200
		})

	if purchase_invoices:
		columns.append({
			"label": "Purchase Invoice",
			"fieldname": "document",
			"fieldtype": "Data",
			"width": 200

		})

	columns.append({
		"label": "Item Code",
		"fieldname": "item_code",
		"fieldtype": "Link",
		"options": "Item",
		"width": 200
	})

	columns.append({
		"label": "Location",
		"fieldname": "location",
		"fieldtype": "Data",
		"width": 250
	})

	return columns