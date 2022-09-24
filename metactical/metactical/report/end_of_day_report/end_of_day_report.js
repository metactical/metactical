// Copyright (c) 2022, Techlift Technologies and contributors
// For license information, please see license.txt
/* eslint-disable */
var today = new Date().toISOString().split('T')[0]
frappe.query_reports["End of Day Report"] = {
	"filters": [
		{
			fieldname: 'date',
			fieldtype: 'Date',
			label: 'Date',
			reqd: 1,
			default: today
		},
		{
			fieldname: 'end_date',
			fieldtype: 'Date',
			label: 'End Date',
			default: today,
			hidden: 1
		}
	]
};
