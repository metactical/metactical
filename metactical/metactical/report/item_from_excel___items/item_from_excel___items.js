// Copyright (c) 2026, Storebuilder Commerce Inc and contributors
// For license information, please see license.txt

frappe.query_reports["Item From Excel - Items"] = {
	"filters": [
		{
			fieldname: "item_from_excel",
			label: __("Item From Excel"),
			fieldtype: "Link",
			options: "Item From Excel",
			reqd: 1
		}
	]
};
