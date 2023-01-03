// Copyright (c) 2023, Techlift Technologies and contributors
// For license information, please see license.txt
/* eslint-disable */

var tday = new Date().toISOString().split('T')[0];
frappe.query_reports["End of Day Report - V2"] = {
	"filters": [
		{
			"fieldname": "date",
			"fieldtype": "Date",
			"label": "Date",
			"reqd": 1,
			default: tday
		}
	]
};
