// Copyright (c) 2023, Techlift Technologies and contributors
// For license information, please see license.txt

cur_frm.fields_dict['stock_entry'].get_query = function(doc, cdt, cdn) {
	return{
		filters:{ 'docstatus': 0}
	}
}

cur_frm.fields_dict['items'].grid.get_field('item_code').get_query = function(doc, cdt, cdn) {
	if(!doc.stock_entry) {
		frappe.throw(__("Please select a Delivery Note"));
	} else {
		return {
			query: "metactical.metactical.doctype.ste_packing_slip.ste_packing_slip.item_details",
			filters:{ 'stock_entry': doc.stock_entry}
		}
	}
}

cur_frm.cscript.get_items = function(doc, cdt, cdn) {
	return this.frm.call({
		doc: this.frm.doc,
		method: "get_items",
		callback: function(r) {
			if(!r.exc) cur_frm.refresh();
		}
	});
}

frappe.ui.form.on('STE Packing Slip', {
	// refresh: function(frm) {

	// }
});
