// Copyright (c) 2024, Techlift Technologies and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Warehouse Stock Report"] = {
	"filters": [
		{
			"fieldname": "warehouse",
			"label": __("Warehouse"),
			"fieldtype": "Link",
			"options": "Warehouse",
			"reqd": 1
		}
	]
};
