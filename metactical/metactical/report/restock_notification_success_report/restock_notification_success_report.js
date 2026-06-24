// Copyright (c) 2026, Storebuilder Commerce Inc and contributors
// For license information, please see license.txt

frappe.query_reports["Restock Notification Success Report"] = {
	"filters": [
		{
			"fieldname": "from_date",
			"label": __("From Date"),
			"fieldtype": "Date",
			"on_change": function () {
				frappe.query_report.refresh();
			},
		},
		{
			"fieldname": "to_date",
			"label": __("To Date"),
			"fieldtype": "Date",
			"on_change": function () {
				frappe.query_report.refresh();
			},
		},
		{
			"fieldname": "lead_source",
			"label": __("Lead Source"),
			"fieldtype": "Data",
		},
		{
			"fieldname": "item_code",
			"label": __("Item Code"),
			"fieldtype": "Link",
			"options": "Item",
		},
		{
			"fieldname": "email_status",
			"label": __("Email Status"),
			"fieldtype": "Select",
			"options": ["", "Delivered", "Opened", "Clicked"].join("\n"),
		},
		{
			"fieldname": "converted",
			"label": __("Converted"),
			"fieldtype": "Select",
			"options": ["All", "Yes", "No"].join("\n"),
			"default": "Yes",
		},
		{
			"fieldname": "conversion_window",
			"label": __("Conversion Window (days)"),
			"fieldtype": "Int",
		},
	]
};
