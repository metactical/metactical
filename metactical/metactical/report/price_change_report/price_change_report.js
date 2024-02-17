// Copyright (c) 2024, Techlift Technologies and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Price Change Report"] = {
	"filters": [
		{
			fieldtype: "Date",
			fieldname: "date",
			label: "Date",
			reqd: 1
		}
	]
};
