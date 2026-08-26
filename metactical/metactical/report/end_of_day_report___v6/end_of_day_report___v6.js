// Copyright (c) 2026, Storebuilder Commerce Inc and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["End of Day Report - V6"] = {
	"filters": [
		{
			"fieldname": "date",
			"fieldtype": "Date",
			"label": "Date",
			"reqd": 1,
			"default": frappe.datetime.get_today()
		}
	],

	formatter: function(value, row, column, data, default_formatter) {
		// HTML columns (user links) are returned as raw HTML from Python
		if (column.fieldtype === "HTML") {
			return value || "";
		}

		var result = default_formatter(value, row, column, data);

		if (data && data.bold) {
			result = `<strong>${result}</strong>`;
		}

		return result;
	}
};
