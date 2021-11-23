// Copyright (c) 2016, Techlift Technologies and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Stock Summary - Custom"] = {
	"filters": [
		{
			"fieldtype": "Link",
			"fieldname": "warehouse",
			"label": "Warehouse",
			"options": "Warehouse",
			"reqd": 1
		},
		{
			"fieldtype": "Data",
			"fieldname": "retail_sku",
			"label": "Retail SKU Suffix"
		}
	]
};
