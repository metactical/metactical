// Copyright (c) 2023, Techlift Technologies and contributors
// For license information, please see license.txt
/* eslint-disable */

var tday = new Date().toISOString().split('T')[0];
frappe.query_reports["End of Day Report - V4"] = {
	"filters": [
		{
			"fieldname": "date",
			"fieldtype": "Date",
			"label": "Date",
			"reqd": 1,
			default: tday
		},
		{
			"fieldname": "end_date",
			"fieldtype": "Date",
			"label": "End Date",
			"reqd": 1,
			default: tday,
			"hidden": 1
        }
	],
	onload: function(report) {
		report.page.add_inner_button(__("Export to Excel"), function() {
			var filters = report.get_values();
			var date = filters.date;
			var url = frappe.urllib.get_full_url(
				"/api/method/metactical.metactical.report.end_of_day_report___v4.end_of_day_report___v4.export_to_excel?"
				+ "date=" + encodeURIComponent(date)
			);
			window.open(url);
		});
	}
};
