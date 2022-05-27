// Copyright (c) 2022, Techlift Technologies and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Buying - Auto Create PO Values"] = {
	"filters": [
		
	],
	onload: function(report){
		console.log(report);
	}
};

function create_po(supplier){
	console.log({"supplier": supplier});
	frappe.call({
		"method": "metactical.metactical.report.buying___auto_create_po_values.buying___auto_create_po_values.create_po",
		"args": {
			"supplier": supplier
		},
		"freeze": true,
		"callback": function(ret){
			console.log({"return": ret});
			frappe.set_route('Form', ret.message.doctype, ret.message.name)
		},
	});
}
