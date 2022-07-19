# Copyright (c) 2022, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
from datetime import datetime, timedelta

def execute(filters=None):
	columns, data = [], []
	columns = [
		{
			"fieldtype": "Link",
			"fieldname": "stock_entry",
			"label": "Stock Entry",
			"options": "Stock Entry",
			"width": "150"
		},
		{
			"fieldtype": "Data",
			"fieldname": "date_created",
			"label": "Date Created",
			"width": "150"
		},
		{
			"fieldtype": "Data",
			"fieldname": "status",
			"label": "Status",
			"width": "150"
		},
		{
			"fieldtype": "Data",
			"fieldname": "aging",
			"label": "Aging",
			"width": "150"
		}
	]
	
	yesterday = datetime.strftime(datetime .today() - timedelta(days=1), '%Y-%m-%d')
	warehouse = filters.get("warehouse")
	data = frappe.db.sql("""SELECT 
								DISTINCT ste.name AS stock_entry, ste.creation AS date_created,
								'Draft' AS status
							FROM
								`tabStock Entry` AS ste
							LEFT JOIN
								`tabStock Entry Detail` AS std ON std.parent = ste.name
							WHERE
								ste.docstatus = 0 AND ste.creation <= %(yesterday)s
								AND std.t_warehouse = %(warehouse)s""",
							{'warehouse': warehouse, 'yesterday': yesterday}, as_dict=1)
	for row in data:
		row.update({
			"date_created": datetime.strftime(row.date_created, '%m-%d-%Y'),
			"aging": abs((datetime.today() - row.date_created).days)
		})
	return columns, data
