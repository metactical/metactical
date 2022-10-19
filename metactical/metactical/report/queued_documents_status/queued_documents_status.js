// Copyright (c) 2022, Techlift Technologies and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Queued Documents Status"] = {
	"filters": [
		{
			"fieldname": "reference",
			"fieldtype": "Select",
			"label": "Reference",
			"options": "Stock Reconciliation\nPurchase Order\nPurchase Invoice\nPurchase Receipt"
		},
		{
			"fieldname": "status",
			"fieldtype": "Select",
			"label": "Queue Status",
			"options": "Not Queued\nQueued\nFailed"
		}
	]
};
