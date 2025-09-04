// Copyright (c) 2023, Techlift Technologies and contributors
// For license information, please see license.txt
/* eslint-disable */

var today = new Date();
var to_date = today.toISOString().split('T')[0];

frappe.query_reports["Sales Report - Stores Restocking V1"] = {
	"filters": [
		{
			"fieldname":"warehouse",
			"label": __("Warehouse"),
			"fieldtype": "Link",
			"options": "Warehouse",
			"width": "100",
			"reqd" : 1,
		}
	] 
}; 

function create_material_request(warehouse){
	frappe.call({
		method: "metactical.metactical.report.sales_report___stores_restocking_v1.sales_report___stores_restocking_v1.create_material_request",
		args: {
			"warehouse": warehouse
		},
		freeze: true,
		callback: function(ret){
			//console.log(ret.message);
			frappe.set_route('Form', ret.message.doctype, ret.message.name)
		}
	});
}