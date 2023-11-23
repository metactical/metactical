// Copyright (c) 2023, Techlift Technologies and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Sales Report V9"] = {
	"filters": [
		{
			"fieldname": "reference_warehouse",
			"fieldtype": "Select",
			"label": "Reference Warehouse",
			"options": "Total QOH\nW01-WHS-Active Stock - ICL\nR05-DTN-Active Stock - ICL\nR07-Queen-Active Stock - ICL\
						\nR06-AMB-Active Stock - ICL\nR04-Mon-Active Stock - ICL\nR03-Vic-Active Stock - ICL\
						\nR02-Edm-Active Stock - ICL\nR01-Gor-Active Stock - ICL",
			"default": "Total QOH",
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
