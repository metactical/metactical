// Copyright (c) 2024, Techlift Technologies and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Item Details Report - V1"] = {
	"filters": [
		{
			"fieldname":"supplier",
			"label": __("Supplier"),
			"fieldtype": "MultiSelectList",
			"options": "Supplier",
			"reqd": 1,
			get_data: function(txt) {
				return frappe.db.get_link_options("Supplier", txt);
			},
		},
		{
			"fieldname": "item_code",
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
		// number of records
		{
			"fieldname":"limit",
			"label": __("Limit"),
			"fieldtype": "Select",
			"options": ["20", "500", "1000", "5000", "10000", "All"],
			"default": "20"
		}
	]
};



// if filters.get("from_date"):
// conditions.append("po.transaction_date >= '{from_date}'".format(from_date=filters.get("from_date")))
// if filters.get("to_date"):
// conditions.append("po.transaction_date <= '{to_date}'".format(to_date=filters.get("to_date")))
// if filters.get("supplier"):
// conditions.append("supplier = '{supplier}'".format(supplier=filters.get("supplier")))
// if filters.get("item_code"):
// conditions.append("poi.item_code = '{item_code}'".format(item_code=filters.get("item_code")))
// if filters.get("retail_sku"):
// conditions.append("`tabItem`.ifw_retailskusuffix = '{retail_sku}'".format(retail_sku=filters.get("retail_sku")))
