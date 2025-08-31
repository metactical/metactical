frappe.ui.form.on('Email Campaign', {
    refresh: function(frm) {
        if (!frm.doc.__islocal) {
            frm.add_custom_button(__('Send Campaign'), function() {
                frappe.call({
                    method: "metactical.custom_scripts.email_campaign.email_campaign.send_email_to_leads_or_contacts",
                    freeze: true,
                    freeze_message: __('Sending Campaign Emails...'),
                    args: {
                        docname: frm.doc.name
                    },
                    callback: function(r) {
                        if (!r.exc) {
                            frappe.msgprint(__('Campaign emails are being sent in the background'));
                        }
                    }
                });
            });
        }
    }
});