frappe.ui.form.on('Contact', {
    validate: function(frm) {
        var phone_nos_valid = true;
        
        // validate phone number + and at least 9 digits
        frm.doc.phone_nos.forEach(function(row) {
            if (!validate_phone(row.phone, row)){
                phone_nos_valid = false;
            }
        })

        if (!phone_nos_valid) {
            frappe.validated = false;
            return;
        }
    }
});

frappe.ui.form.on('Contact Phone', {
    phone: function(frm, cdt, cdn) {
        if (frm.doc.__islocal) {
            // validate phone number + and at least 9 digits
            var phone = locals[cdt][cdn].phone;
            validate_phone(phone, locals[cdt][cdn]);
        }
    }
});

let validate_phone = function(phone, row) {
    if (!phone.match(/^\+\d{9,}$/)) {
        frappe.msgprint(__('Invalid Phone Number. Phone number must start with + and have at least 9 digits.'));
        return false;
    }

    return true;
}