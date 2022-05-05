// Copyright (c) 2016, Techlift Technologies and contributors
// For license information, please see license.txt
/* eslint-disable */

var today = new Date();
var to_date = today.toISOString().split('T')[0];

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
			"default": to_date
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
