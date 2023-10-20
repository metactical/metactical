// Copyright (c) 2023, Techlift Technologies and contributors
// For license information, please see license.txt

frappe.ui.form.on('Manifest', {
	refresh: function (frm) {
		frm.set_query("pickup_address", () => {
			return {
				filters: {
					is_your_company_address: 1
				}
			}
		});
		frm.events.show_shipment_button(frm);
		frm.events.show_manifest_button(frm);
	},
	
	show_shipment_button: function(frm){
		if(!frm.doc.__islocal && !frm.doc.po_number && frm.doc.status != "Completed"){
			frm.add_custom_button(__("Get Shipments"), () => {
				frappe.call({
					method: "metactical.metactical.doctype.manifest.manifest.get_shipments",
					args: {
						"pickup_date": frm.doc.pickup_date,
						"warehouse": frm.doc.warehouse
					},
					freeze: true,
					callback: function(ret){
						let shipments = ret.message.shipments;
						if(!frm.doc.pickup_contact_person){
							frm.set_value("pickup_contact_person", ret.message.pickup_contact_person);
						}
						frm.doc.items = []
						shipments.forEach(function(row){
							frm.add_child("items", {
								"shipment": row.shipment_name,
								"shipment_id": row.shipment_id,
								"status": "Not Transmitted"
							});
						});
						frm.refresh_field("items");
						frm.save()
					}
				});
			});
		}
	},
	
	show_manifest_button: function(frm){
		if (frm.doc.items?.length && !frm.doc.po_number && frm.doc.status != "Completed") {
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
		else if(frm.doc.status == "Completed"){
			frm.add_custom_button(__("Re-download Manifest"), () => {
				if(frm.doc.__unsaved == 1){
					frappe.msgprint("Please save the document first");
				}
				else{
					frappe.call({
						method: "metactical.metactical.doctype.manifest.manifest.redownload_manifest",
						args: {
							"docname": frm.docname
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
	},
	
	pickup_address: function(frm){
		if(frm.doc.pickup_address){
			erpnext.utils.get_address_display(frm, 'pickup_address', 'pickup_address_display', true);
		}
	},
	
	warehouse: function(frm){
		frappe.call({
			method: "metactical.metactical.doctype.manifest.manifest.get_warehouse_address",
			args: {
				warehouse: frm.doc.warehouse
			},
			freeze: true,
			callback: function(ret){
				frm.set_value("pickup_address", ret.message);
			}
		});
	}
});
