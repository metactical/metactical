frappe.ui.form.on('POS Profile User', {
    neb_send_welcome_email: function(frm, cdt, cdn) {
        var row = locals[cdt][cdn];
        frappe.call({
            method: "metactical.custom_scripts.pos_profile.pos_profile.send_welcome_email",
            args: {
                user: row.user,
                profile: frm.doc.name
            },
            freeze: true,
            freeze_message: __("Sending Welcome Email..."),
            callback: function(res) {
                if (res.url){
                    frappe.utils.copy_to_clipboard(res.url);
                    frappe.set_alert(__("Branch Pairing Link Copied to Clipboard"), 5);
                }
            }
        });
    }
});