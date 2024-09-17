// Copyright (c) 2024, Techlift Technologies and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Item Price Excel - V3"] = {
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
						frappe.query_report.set_filter_value('quotation', []);
						frappe.query_report.set_filter_value('supplier', frappe.query_report.get_filter_value('supplier'));
					}
				}
				frappe.query_report.refresh();
			}
		},
		{
			"label": "Supplier Price List",
			"fieldname": "supplier_price_list",
			"fieldtype": "MultiSelectList",
			"options": "Price List",
			"mandatory_based_on": "eval: doc.supplier",
			get_data: function(txt) {
				return frappe.db.get_link_options("Price List", txt, {
					"name": ["like", "SUP%"]
				});
			},
		},
		{
			"label": "Quotation",
			"fieldname": "quotation",
			"fieldtype": "MultiSelectList",
			"options": "Quotation",
			on_change: () => {
				// remove supplier filter value if quotation is selected
				if (frappe.query_report.get_filter_value('quotation')){
					if (frappe.query_report.get_filter_value('supplier'))
						frappe.query_report.set_filter_value('supplier', "");

					if (frappe.query_report.get_filter_value('purchase_order'))
						frappe.query_report.set_filter_value('purchase_order', []);

					if (frappe.query_report.get_filter_value('sales_order'))
						frappe.query_report.set_filter_value('sales_order', []);

					if (!frappe.query_report.get_filter_value('supplier') && 
						!frappe.query_report.get_filter_value('purchase_order' &&
						!frappe.query_report.get_filter_value('sales_order')
						)){
						frappe.query_report.refresh();
					}
				}
			},
			get_data: function(txt) {
				return frappe.db.get_link_options("Quotation", txt);
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

					if (frappe.query_report.get_filter_value("quotation"))
						frappe.query_report.set_filter_value("quotation", []);

					if (!frappe.query_report.get_filter_value('supplier') 
						&& !frappe.query_report.get_filter_value('sales_order') 
						&& !frappe.query_report.get_filter_value('quotation')){
						frappe.query_report.refresh();
					}
				}
			},
			get_data: function(txt) {
				return frappe.db.get_link_options("Purchase Order", txt);
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

					if (frappe.query_report.get_filter_value("supplier_price_list"))
						frappe.query_report.set_filter_value("supplier_price_list", []);
					
					if (frappe.query_report.get_filter_value("quotation"))
						frappe.query_report.set_filter_value("quotation", []);

					if (!frappe.query_report.get_filter_value('supplier') && 
					!frappe.query_report.get_filter_value('purchase_order') &&
					!frappe.query_report.get_filter_value('quotation')){
						frappe.query_report.refresh();
					}
				}
			},
			get_data: function(txt) {
				return frappe.db.get_link_options("Sales Order", txt);
			}
		},
		{
			"label": "Retail Price List",
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