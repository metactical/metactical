// Copyright (c) 2023, Techlift Technologies and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["QBO Import Report"] = {
	"filters": [
		{
			"fieldname": "start_date",
			"fieldtype": "Date",
			"label": "Start Date",
			"reqd": 1
		},
		{
			"fieldname": "end_date",
			"fieldtype": "Date",
			"label": "End Date",
			"reqd": 1
		},
		{
			"fieldname": "company",
			"fieldtype": "Link",
			"label": "Company",
			"options": "Company",
			"default": frappe.defaults.get_user_default("Company"),
			"reqd": 1
		}
	]
};
