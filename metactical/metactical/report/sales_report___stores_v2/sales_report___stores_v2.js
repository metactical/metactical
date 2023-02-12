// Copyright (c) 2023, Techlift Technologies and contributors
// For license information, please see license.txt
/* eslint-disable */

var today = new Date();
var to_date = today.toISOString().split('T')[0];

frappe.query_reports["Sales Report - Stores V2"] = {
	"filters": [
		{
			"fieldname":"pos_profile",
			"label": __("Pos Profile"),
			"fieldtype": "Link",
			"options": "POS Profile",
			"width": "100",
			"reqd" : 0,
		},
		{
			"fieldname": "to_date",
			"fieldtype": "Date",
			"label": __("To Date"),
			"default": to_date,
			"reqd": 1
		},
		{
			"fieldname":"item_code",
			"label": __("Item"),
			"fieldtype": "Link",
			"options": "Item",
			"width": "100",
		},
	]
};

function create_material_transfer(pos_profile, to_date, item_code){
	frappe.call({
		method: "metactical.metactical.report.sales_report___stores_v2.sales_report___stores_v2.create_material_transfer",
		args: {
			"pos_profile": pos_profile,
			"to_date": to_date,
			"item_code": item_code
		},
		freeze: true,
		callback: function(ret){
			//console.log(ret.message);
			frappe.set_route('Form', ret.message.doctype, ret.message.name)
		}
	});
}
