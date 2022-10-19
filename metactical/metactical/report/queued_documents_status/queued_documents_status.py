# Copyright (c) 2022, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe

def execute(filters=None):
	columns, data = [], []
	columns = get_columns(filters)
	data = get_data(filters)
	return columns, data
	
def get_columns(filters):
	columns = [
		{
			"fieldname": "reference",
			"fieldtype": "Link",
			"options": "Doctype",
			"label": "Reference",
			"width": 150
		},
		{
			"fieldname": "reference_name",
			"fieldtype": "Dynamic Link",
			"options": "reference",
			"label": "Reference Name",
			"width": 150
		},
		{
			"fieldname": "queue_status",
			"fieldtype": "Select",
			"label": "Queued Status",
			"width": 150
		},
		{
			"fieldname": "submitted_by",
			"fieldtype": "Link",
			"options": "Doctype",
			"label": "Submitted By",
			"width": 150
		}
	]
	return columns
	

def get_data(filters):
	where = ""
	if filters.get("status") is not None and filters.get("status") != "":
		where = " AND ais_queue_status = '{}' ".format(filters.get("status"))
	
	references = ["Stock Reconciliation", "Purchase Order", "Purchase Invoice", "Purchase Receipt"]
	reference = filters.get("reference")
	if reference and reference != "":
		references = [reference]
	pos, prs, pis, srs = [], [], [], []
	if "Purchase Order" in references:
		pos = frappe.db.sql("""SELECT 
									'Purchase Order' AS reference, name AS reference_name, 
									modified_by AS submitted_by, ais_queue_status AS queue_status
								FROM
									`tabPurchase Order`
								WHERE
									docstatus = 0 """ + where + """
								ORDER BY modified DESC
								""", as_dict=1)
	
	if "Purchase Receipt" in references:						
		prs = frappe.db.sql("""SELECT 
									'Purchase Receipt' AS reference, name AS reference_name, 
									modified_by AS submitted_by, ais_queue_status AS queue_status
								FROM
									`tabPurchase Receipt`
								WHERE
									docstatus = 0 """ + where + """
								ORDER BY modified DESC
								""", as_dict=1)
	
	if "Purchase Invoice" in references:						
		pis = frappe.db.sql("""SELECT 
									'Purchase Invoice' AS reference, name AS reference_name, 
									modified_by AS submitted_by, ais_queue_status AS queue_status
								FROM
									`tabPurchase Invoice`
								WHERE
									docstatus = 0 """ + where + """
								ORDER BY modified DESC
								""", as_dict=1)
	
	if "Stock Reconciliation" in references:						
		srs = frappe.db.sql("""SELECT 
									'Stock Reconciliation' AS reference, name AS reference_name, 
									modified_by AS submitted_by, ais_queue_status AS queue_status
								FROM
									`tabStock Reconciliation`
								WHERE
									docstatus = 0 """ + where + """
								ORDER BY modified DESC
								""", as_dict=1)
							
	data = pos + prs + pis + srs
	return data

