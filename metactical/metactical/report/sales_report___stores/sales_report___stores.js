// Copyright (c) 2016, Techlift Technologies and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Sales Report - Stores"] = {
	"filters": [
		{
			"fieldname":"pos_profile",
			"label": __("Pos Profile"),
			"fieldtype": "Link",
			"options": "POS Profile",
			"width": "100",
			"reqd" : 0,
		},
		{
			"fieldname": "to_date",
			"fieldtype": "Date",
			"label": __("To Date"),
			"reqd" : 1,
		},
		{
			"fieldname":"item_code",
			"label": __("Item"),
			"fieldtype": "Link",
			"options": "Item",
			"width": "100",
		},
	]
};
