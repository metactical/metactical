# Copyright (c) 2022, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe

def execute(filters=None):
	columns, data = [], []
	columns = get_columns(filters)
	data = get_pos(filters)
	return columns, data

def get_data(filters):
	suppliers = frappe.db.sql("""
						SELECT
							name AS supplier
						FROM
							`tabSupplier`
						WHERE
							disabled = 0
						""", as_dict=1)
	data = []
	for row in suppliers:
		row_data = get_last_po(row.supplier)
		data.append(row.update(row_data))
	return data

def get_last_po(supplier):
	data = frappe.db.sql("""SELECT
								po.name AS recent_po, po.transaction_date AS po_date,
								pr.name AS recent_pr, pr.status AS pr_status, po.eta_date AS eta,
								po.carrier_used, po.tracking_id, po.drop_ship_notes AS notes
							FROM
								`tabPurchase Order` AS po
							LEFT JOIN
								`tabPurchase Receipt` AS pr ON pr.purchase_order = po.name
							WHERE
								po.docstatus = 1 AND po.supplier = %(supplier)s
							ORDER BY
								po.transaction_date DESC
							LIMIT 1""", {"supplier": supplier}, as_dict=1)
	if len(data) > 0:
		return data[0]
	else:
		return frappe._dict()
		
def get_pos(filters):
	data = frappe.db.sql("""SELECT
								po.supplier, po.name AS po_no, po.transaction_date AS po_date,
								pr.name AS recent_pr, pr.status AS pr_status, po.eta_date AS eta,
								po.carrier_used, po.tracking_id, po.drop_ship_notes AS notes
							FROM
								`tabPurchase Order` AS po
							LEFT JOIN
								`tabPurchase Receipt` AS pr ON pr.purchase_order = po.name
							WHERE
								po.docstatus = 1 AND po.status <> 'Completed'
							ORDER BY
								po.supplier, po.transaction_date DESC
							""", as_dict=1)
	return data

def get_columns(filters):
	columns = [
		{
			"fieldname": "supplier",
			"fieldtype": "Link",
			"label": "Supplier",
			"options": "Supplier",
			"width": 150
		},
		{
			"fieldname": "po_no",
			"fieldtype": "Link",
			"label": "PO Number",
			"options": "Purchase Order",
			"width": 150
		},
		{
			"fieldname": "po_date",
			"fieldtype": "Date",
			"label": "PO Date",
			"width": 150
		},
		{
			"fieldname": "recent_pr",
			"fieldtype": "Link",
			"label": "PR Number",
			"options": "Purchase Receipt",
			"width": 150
		},
		{
			"fieldname": "pr_status",
			"fieldtype": "Data",
			"label": "PR Status",
			"width": 150
		},
		{
			"fieldname": "eta",
			"fieldtype": "Data",
			"label": "ETA",
			"width": 150
		},
		{
			"fieldname": "carrier_used",
			"fieldtype": "Data",
			"label": "Carrier Used",
			"width": 150
		},
		{
			"fieldname": "tracking_id",
			"fieldtype": "Data",
			"label": "Tracking ID",
			"width": 150
		},
		{
			"fieldname": "notes",
			"fieldtype": "Data",
			"label": "Notes",
			"width": 150
		}
	]
	return columns
