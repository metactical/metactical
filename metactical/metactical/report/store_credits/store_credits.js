// Copyright (c) 2024, Techlift Technologies and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Store Credits"] = {
	"filters": [
		{
			"fieldname": "customer",
			"label": __("Customer"),
			"fieldtype": "Link",
			"options": "Customer",
			"mandatory_depends_on": "eval:!fetch_all"
		},
		{
			"fieldname": "sales_invoice",
			"label": __("Sales Invoice"),
			"fieldtype": "Link",
			"options": "Sales Invoice",
			"get_query": () => {
				return {
					filters: [["is_return", "=", 1], ["docstatus", "=", 1]]
				}
			},
			on_change: () => {
				if (frappe.query_report.get_filter_value('sales_invoice')){
					frappe.query_report.set_filter_value('customer', "");
					frappe.query_report.set_filter_value('email', "");
					frappe.query_report.set_filter_value("phone", "");
					frappe.query_report.set_filter_value("fetch_all", 0)
				}
				frappe.query_report.refresh();
			}
		},
		{
			"fieldname": "email",
			"label": __("Email"),
			"fieldtype": "Data",
		},
		{
			"fieldname": "phone",
			"label": __("Phone"),
			"fieldtype": "Data",
		},
		{
			"fieldname": "fetch_all",
			"label": __("Fetch All"),
			"fieldtype": "Check",
			"default": 0,
			on_change: () => {
				if (frappe.query_report.get_filter_value('fetch_all')){
					frappe.query_report.set_filter_value('customer', "");
					frappe.query_report.set_filter_value('email', "");
					frappe.query_report.set_filter_value("phone", "");
					frappe.query_report.set_filter_value("sales_invoice", "")
				}
				frappe.query_report.refresh();
			}
		}
	]
};
