// Copyright (c) 2022, Techlift Technologies and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Sales Report - USA"] = {
	"filters": [
		{
			"fieldname": "reference_warehouse",
			"fieldtype": "Select",
			"label": "Reference Warehouse",
			"options": "US02-Houston - Active Stock - ICL",
			"default": "US02-Houston - Active Stock - ICL",
			"reqd": 1
		},
		{
			"fieldname":"supplier",
			"label": __("Supplier"),
			"fieldtype": "MultiSelectList",
			"options": "Supplier",
			get_data: function(txt) {
				// if (!frappe.query_report.filters) return;

				// let party_type = frappe.query_report.get_filter_value('party_type');
				// if (!party_type) return;

				return frappe.db.get_link_options("Supplier", txt);
			},
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
