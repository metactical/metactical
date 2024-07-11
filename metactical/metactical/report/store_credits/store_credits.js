// Copyright (c) 2024, Techlift Technologies and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Store Credits"] = {
	"filters": [
		{
			"fieldname": "customer",
			"label": __("Customer"),
			"fieldtype": "Link",
			"options": "Customer",
			"mandatory_depends_on": "eval:!fetch_all"
		},
		{
			"fieldname": "email",
			"label": __("Email"),
			"fieldtype": "Data",
		},
		{
			"fieldname": "phone",
			"label": __("Phone"),
			"fieldtype": "Data",
		},
		{
			"fieldname": "fetch_all",
			"label": __("Fetch All"),
			"fieldtype": "Check",
			"default": 0
		}
	]
};
