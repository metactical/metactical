// Copyright (c) 2024, Techlift Technologies and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Current Stock Report - V1"] = {
	"filters": [
		{
			"fieldname":"item_code",
			"label": __("Item Code"),
			"fieldtype": "Link",
			"options": "Item",
			get_query: function() {
				return {
					filters: {
						"has_variants": 0
					}
				};
			}
		},
		{
			"fieldname":"ifw_retailskusuffix",
			"label": __("Retail SKU"),
			"fieldtype": "Data"
		},
		{
			"fieldname":"warehouse",
			"label": __("Warehouse"),
			"fieldtype": "Link",
			"options": "Warehouse"
		},
		{
			"fieldname":"limit",
			"label": __("Limit"),
			"fieldtype": "Select",
			"options": ["20", "500", "1000", "5000", "10000", "All"],
			"default": "20"
		}
	]
};


// Item_code	Retail_sku	Available_Qty	Warehouse
