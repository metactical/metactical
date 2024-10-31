// Copyright (c) 2024, Techlift Technologies and contributors
// For license information, please see license.txt


frappe.provide("metactical.PurchaseOrderImportTool");
frappe.provide("erpnext.buying");
frappe.provide("erpnext.accounts.dimensions");
{% include 'erpnext/public/js/controllers/buying.js' %};

frappe.ui.form.on('Purchase Order Import Tool', {
	// refresh: function(frm) {

	// }
});


metactical.PurchaseOrderImportTool = class PurchaseOrderImportTool extends erpnext.buying.BuyingController{
	setup() {

	}

	onload(){

	}

	refresh() {

	}

	taxes_and_charges() {

	}

	apply_price_list(item, reset_plc_conversion) {
		// We need to reset plc_conversion_rate sometimes because the call to
		// `erpnext.stock.get_item_details.apply_price_list` is sensitive to its value
		if (!reset_plc_conversion) {
			this.frm.set_value("plc_conversion_rate", "");
		}

		var me = this;
		var args = this._get_args(item);
		if (!((args.items && args.items.length) || args.price_list)) {
			return;
		}

		if (me.in_apply_price_list == true) return;

		me.in_apply_price_list = true;
		return this.frm.call({
			method: "erpnext.stock.get_item_details.apply_price_list",
			args: {	args: args },
			callback: function(r) {
				if (!r.exc) {
					frappe.run_serially([
						() => me.frm.set_value("price_list_currency", r.message.parent.price_list_currency),
						() => me.frm.set_value("plc_conversion_rate", r.message.parent.plc_conversion_rate),
						() => { me.in_apply_price_list = false; }
					]);

				} else {
					me.in_apply_price_list = false;
				}
			}
		}).always(() => {
			me.in_apply_price_list = false;
		});
	}

	shipping_address(){
		
	}
};

extend_cscript(cur_frm.cscript, new metactical.PurchaseOrderImportTool({frm: cur_frm}));