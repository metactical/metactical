// Copyright (c) 2021, Techlift Technologies and contributors
// For license information, please see license.txt

frappe.ui.form.on('Shipstation Settings', {
	refresh: function(frm) {
		frm.events.show_hide_fields(frm);
	},
	
	shipping_charges_specified: function(frm) {
		frm.events.show_hide_fields(frm);
	},
	
	show_hide_fields: function(frm) {
		if(frm.doc.shipping_charges_specified){
			var charges_specified = frm.doc.shipping_charges_specified;
			frm.toggle_display('shipping_item', charges_specified=="In Item Table");
			frm.toggle_display('shipping_charge', charges_specified=="In Charges Table");
		}
	}
});
