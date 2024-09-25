// Copyright (c) 2024, Techlift Technologies and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Item Locations"] = {
	"filters": [
		{
			"label": "Purchase Order",
			"fieldname": "purchase_order",
			"fieldtype": "MultiSelectList",
			"options": "Purchase Order",
			on_change: () => {
				// remove supplier filter value if purchase order is selected
				if (frappe.query_report.get_filter_value('purchase_order')){
					if(frappe.query_report.get_filter_value('purchase_receipt'))
						frappe.query_report.set_filter_value('purchase_receipt', []);
					
					frappe.query_report.set_filter_value('purchase_order', frappe.query_report.get_filter_value('purchase_order'));
				}
			},
			get_data: function(txt) {
				return frappe.db.get_link_options("Purchase Order", txt);
			}
		},
		{
			"label": "Purchase Receipt",
			"fieldname": "purchase_receipt",
			"fieldtype": "MultiSelectList",
			"options": "Purchase Receipt",
			on_change: () => {
				// remove supplier filter value if purchase receipt is selected
				if (frappe.query_report.get_filter_value('purchase_receipt')){
					if(frappe.query_report.get_filter_value('purchase_order'))
						frappe.query_report.set_filter_value('purchase_order', []);

					frappe.query_report.set_filter_value('purchase_receipt', frappe.query_report.get_filter_value('purchase_receipt'));
				}
			},
			get_data: function(txt) {
				return frappe.db.get_link_options("Purchase Receipt", txt);
			}
		},
	]
};
