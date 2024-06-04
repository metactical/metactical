// Copyright (c) 2024, Techlift Technologies and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Price Lists - V2"] = {
	"filters": [
		{
			"label": "Supplier",
			"fieldname": "supplier",
			"fieldtype": "Link",
			"options": "Supplier",
			on_change: () => {
				// remove purchase order filter value if supplier is selected
				if (frappe.query_report.get_filter_value('supplier')){
					if (frappe.query_report.get_filter_value('purchase_order')){
						frappe.query_report.set_filter_value('purchase_order', []);
						frappe.query_report.set_filter_value('sales_order', []);
						frappe.query_report.set_filter_value('supplier', frappe.query_report.get_filter_value('supplier'));
					}
				}
				frappe.query_report.refresh();
			}
		},
		{
			"label": "Purchase Order",
			"fieldname": "purchase_order",
			"fieldtype": "MultiSelectList",
			"options": "Purchase Order",
			on_change: () => {
				// remove supplier filter value if purchase order is selected
				if (frappe.query_report.get_filter_value('purchase_order')){
					if (frappe.query_report.get_filter_value('supplier'))
						frappe.query_report.set_filter_value('supplier', "");

					if (frappe.query_report.get_filter_value('sales_order'))
						frappe.query_report.set_filter_value('sales_order', []);

					if (!frappe.query_report.get_filter_value('supplier') && !frappe.query_report.get_filter_value('sales_order')){
						frappe.query_report.refresh();
					}
				}
			},
			get_data: function(txt) {
				return frappe.db.get_link_options("Purchase Order");
			}
		},
		{
			"label": "Sales Order",
			"fieldname": "sales_order",
			"fieldtype": "MultiSelectList",
			"options": "Sales Order",
			on_change: () => {
				// remove supplier filter value if sales order is selected
				if (frappe.query_report.get_filter_value('sales_order')){
					if (frappe.query_report.get_filter_value('supplier'))
						frappe.query_report.set_filter_value('supplier', "");

					if (frappe.query_report.get_filter_value('purchase_order'))
						frappe.query_report.set_filter_value('purchase_order', []);


					if (!frappe.query_report.get_filter_value('supplier') && !frappe.query_report.get_filter_value('purchase_order')){
						frappe.query_report.refresh();
					}
				}
			},
			get_data: function(txt) {
				return frappe.db.get_link_options("Sales Order");
			}
		},
		{
			"label": "Price List",
			"fieldname": "price_list",
			"fieldtype": "MultiSelectList",
			"options": "Price List",
			get_data: function(txt) {
				return frappe.db.get_link_options("Price List", txt, {
					"name": ["like", "RET%"]
				});
			},
		}
	]
};
