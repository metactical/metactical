frappe.ui.form.on('Delivery Note', {
    refresh: frm => {
        if (!frm.doc.is_return && frm.doc.status != "Closed" && frm.doc.docstatus === 0) {
            // Add Shipment Button
            frm.add_custom_button(__('Shipment'), function () {
                frappe.model.open_mapped_doc({
                    method: "metactical.utils.shipping.shipping.make_shipment",
                    frm: frm
                })
            }, __('Create'));
        }

        if (frm.doc.docstatus == 0){
			frm.add_custom_button("Submit", () => {
				frappe.call({
					method: "metactical.custom_scripts.delivery_note.delivery_note.submit_delivery_note",
					args: {
						"doc": frm.doc.name
					},
				})
			});
		}
    }
})

cur_frm.cscript.make_shipment = function () {
    frappe.model.open_mapped_doc({
        method: "metactical.utils.shipping.shipping.make_shipment",
        frm: cur_frm
    })
}

