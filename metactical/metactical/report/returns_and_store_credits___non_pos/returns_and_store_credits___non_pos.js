// Copyright (c) 2023, Techlift Technologies and contributors
// For license information, please see license.txt
/* eslint-disable */
var aday = new Date();
var to_date = aday.toISOString().split('T')[0];
aday.setDate(aday.getDate() - 1);
var from_date = aday.toISOString().split('T')[0];

frappe.query_reports["Returns and Store Credits - Non POS"] = {
	"filters": [
		{
			fieldname: "from_date",
			fieldtype: "Date",
			label: "From Date",
			reqd: 1,
			default: from_date
		},
		{
			fieldname: "to_date",
			fieldtype: "Date",
			label: "To Date",
			reqd: 1,
			default: to_date
		},
		{
			fieldname: "source",
			fieldtype: "Link",
			label: "Source",
			options: "Lead Source"
		}
	]
};
