// Copyright (c) 2016, Techlift Technologies and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Sales Report by Location"] = {
	"filters": [
		{
			fieldtype: "Date",
			fieldname: "from_date",
			label: "From Date",
			reqd: 1
		},
		{
			fieldtype: "Date",
			fieldname: "to_date",
			label: "To Date",
			reqd: 1
		},
		{
			fieldtype: "Link",
			fieldname: "warehouse",
			options: "Warehouse",
			label: "Location"
		},
		{
			fieldtype: "Link",
			fieldname: "supplier",
			options: "Supplier",
			label: "Supplier"
		}
	]
};
