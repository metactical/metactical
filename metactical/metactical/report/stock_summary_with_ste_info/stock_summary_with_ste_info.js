// Copyright (c) 2016, Techlift Technologies and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Stock Summary With STE Info"] = {
	"filters": [
		{
			"fieldtype": "Link",
			"fieldname": "warehouse",
			"label": "Warehouse",
			"options": "Warehouse",
			"reqd": 1
		}
	]
};
