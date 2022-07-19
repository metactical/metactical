// Copyright (c) 2022, Techlift Technologies and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["STE Draft Report"] = {
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
