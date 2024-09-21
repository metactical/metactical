// Copyright (c) 2024, Techlift Technologies and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Pricing Rule Report - V1"] = {
	"filters": [
		{
			"fieldname": "apply_on",
			"label": __("Apply On"),
			"fieldtype": "Select",
			"options": "\nItem Code\nItem Group\nBrand",
			"reqd": 1
		},
		{
			"fieldname": "item_group",
			"label": __("Item Group"),
			"fieldtype": "MultiSelectList",
			"options": "Item Group",
			"depends_on": "eval:doc.apply_on == 'Item Group'",
			"mandatory_depends_on": "eval:doc.apply_on == 'Item Group'",
			get_data: function(txt) {
				return frappe.db.get_link_options("Item Group", txt);
			}
		},
		{
			"fieldname": "brand",
			"label": __("Brand"),
			"fieldtype": "MultiSelectList",
			"options": "Brand",
			"depends_on": "eval:doc.apply_on == 'Brand'",
			"mandatory_depends_on": "eval:doc.apply_on == 'Brand'",
			get_data: function(txt) {
				return frappe.db.get_link_options("Brand", txt);
			}
		},
		{
			"fieldname": "item_code",
			"label": __("Item Code"),
			"fieldtype": "MultiSelectList",
			"options": "Item",
			"depends_on": "eval:doc.apply_on == 'Item Code'",
			"mandatory_depends_on": "eval:doc.apply_on == 'Item Code'",
			get_data: function(txt) {
				return frappe.db.get_link_options("Item", txt);
			}
		}
	]
};
