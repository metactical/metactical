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
    }
})

cur_frm.cscript.make_shipment = function () {
    frappe.model.open_mapped_doc({
        method: "metactical.utils.shipping.shipping.make_shipment",
        frm: cur_frm
    })
}