// Copyright (c) 2022, Techlift Technologies and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Full Time Log"] = {
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
			"fieldname": "employee",
			"label": "Employee",
			"options": "Employee",
			"reqd": 1
		}
	]
};
