// Copyright (c) 2023, Techlift Technologies and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Sales Report Based on Delivery Note"] = {
	"filters": [
		{
			"fieldtype": "Date",
			"fieldname": "start_date",
			"label": "Start Date",
			"reqd": 1
		},
		{
			"fieldtype": "Date",
			"fieldname": "end_date",
			"label": "End Date",
			"reqd": 1
		},
		{
			"fieldtype": "Link",
			"fieldname": "source",
			"label": "Source",
			"options": "Lead Source"
		},
		{
			"fieldtype": "Link",
			"fieldname": "warehouse",
			"label": "Warehouse",
			"options": "Warehouse"
		}
	]
};
