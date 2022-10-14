// Copyright (c) 2022, Techlift Technologies and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Queued Docs With Errors"] = {
	"filters": [
		{
			fieldtype: "Select",
			fieldname: "reference",
			label: "Document Type",
			options: "Stock Reconciliation\nPurchase Order\nPurchase Invoice\nPurchase Receipt"
		}
	]
};
