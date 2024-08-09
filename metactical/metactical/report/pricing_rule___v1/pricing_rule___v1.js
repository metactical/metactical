// Copyright (c) 2024, Techlift Technologies and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Pricing Rule - V1"] = {
	"filters": [
		{
			"fieldname": "item_group",
			"label": __("Item Group"),
			"fieldtype": "MultiSelectList",
			"options": "Item Group",
			"reqd": 1,
			get_data: function(txt) {
				return frappe.db.get_link_options("Item Group", txt);
			}
		},
		{
			"fieldname": "supplier",
			"label": __("Supplier"),
			"fieldtype": "Link",
			"options": "Supplier",
			"reqd": 1,
		}
	]
};
