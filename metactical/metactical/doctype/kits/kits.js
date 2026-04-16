// Copyright (c) 2026, Storebuilder Commerce Inc and contributors
// For license information, please see license.txt

frappe.ui.form.on("Kits", {
	refresh(frm) {
        frm.set_query("item_code", "kit_items", function() {
            return {
                filters: {
                    has_variants: 1
                }
            }
        });

        frm.set_query("kit_item", function(){
            return {
                filters: {
                    is_stock_item: 0
                }
            }
        });
	},
});

frappe.ui.form.on("Product Bundle Item", {
    item_code: function(frm, cdt, cdn){
        let row = locals[cdt][cdn];
        row.qty = 1;
        frm.refresh_field("kit_items");
    }
});