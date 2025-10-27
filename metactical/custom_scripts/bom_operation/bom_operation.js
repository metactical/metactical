frappe.ui.form.on("Sub Operation", {
    sub_operations_add(frm, cdt, cdn){
        var row = locals[cdt][cdn]
        row.workstation = frm.doc.workstation
    }
})