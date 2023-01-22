// Copyright (c) 2022, Techlift Technologies and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Unsynced Delivery Notes With SS"] = {
	"filters": [

	]
};

function resync_shipstation(delivery_note){
	console.log({"reports": frappe.query_reports["Unsynced Delivery Notes With SS"]});
	frappe.call({
		method: "metactical.api.shipstation.create_shipstation_orders",
		args: {"order_no": delivery_note},
		freeze: true,
		callback: function(ret){
			frappe.msgprint("The Delivery Note has been resynced with Shipstation. Please refresh the report.");
		}
	});
}
