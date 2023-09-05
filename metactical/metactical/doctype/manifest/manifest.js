// Copyright (c) 2023, Techlift Technologies and contributors
// For license information, please see license.txt

frappe.ui.form.on('Manifest', {
	refresh: function (frm) {
		if (frm.doc.items?.length && !frm.doc.po_number) {
			frm.add_custom_button(__("Make Manifest"), () => {
				if(frm.doc.__unsaved == 1){
					frappe.msgprint("Please save the document first");
				}
				else{
					frappe.call({
						method: "metactical.metactical.doctype.manifest.manifest.create_manifest",
						args: {
							"manifest": frm.docname
						},
						freeze: true,
						callback: function(ret){
							console.log(ret);
							frm.reload_doc();
						}
					});
				}
			})
		}
		frm.toggle_display("get_shipments", !frm.doc.__islocal);
	},
	
	get_shipments: function(frm){
		frappe.call({
			method: "metactical.metactical.doctype.manifest.manifest.get_shipments",
			args: {
				"pickup_date": frm.doc.pickup_date,
				"warehouse": frm.doc.warehouse
			},
			freeze: true,
			callback: function(ret){
				let shipments = ret.message.shipments;
				frm.set_value("pickup_company", ret.message.pickup_company);
				frm.set_value("pickup_address", ret.message.pickup_address_name);
				frm.set_value("pickup_contact_person", ret.message.pickup_contact_person);
				shipments.forEach(function(row){
					frm.add_child("items", {
						"shipment": row.shipment_name,
						"shipment_id": row.shipment_id,
						"status": "Not Transmitted"
					});
				});
				frm.refresh_field("items");
			}
		});
	},
	
	pickup_address: function(frm){
		if(frm.doc.pickup_address){
			erpnext.utils.get_address_display(frm, 'pickup_address', 'pickup_address_display', true);
		}
	}
});
