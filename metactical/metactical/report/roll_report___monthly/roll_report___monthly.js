// Copyright (c) 2016, Techlift Technologies and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Roll report - Monthly"] = {
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
		}
	]
};
