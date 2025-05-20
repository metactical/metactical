// Copyright (c) 2025, Techlift Technologies and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Search by Location"] = {
	"filters": [
		{
			"fieldname": "location_starts_with",
			"label": __("Location (Starts With)"),
			"fieldtype": "Data"
		},
		{
			"fieldname": "location_includes",
			"label": __("Location (Includes)"),
			"fieldtype": "Data"
		},
		{
			"fieldname": "retail_sku",
			"label": __("Retail SKU"),
			"fieldtype": "Data"
		},
		{
			"fieldname": "warehouse",
			"label": __("Warehouse"),
			"fieldtype": "Link",
			"options": "Warehouse",
			"default": "W01-WHS-Active Stock - ICL"
		}
	]
};
