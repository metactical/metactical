# Copyright (c) 2022, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe

def execute(filters=None):
	columns, data = [], []
	columns = get_columns(filters)
	pos = get_pos(filters)
	pos_in_data = []
	for row in pos:
		if row.po_no not in pos_in_data:
			pos_in_data.append(row.po_no)
			data.append(row)
	return columns, data
		
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
								po.docstatus = 1 AND po.status NOT IN ('Completed', 'Closed', 'Delivered')
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
