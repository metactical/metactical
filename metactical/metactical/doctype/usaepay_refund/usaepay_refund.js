// Copyright (c) 2026, Storebuilder Commerce Inc and contributors
// For license information, please see license.txt

frappe.ui.form.on("USAePay Refund", {
	refresh(frm) {
            frm.page.set_indicator(`${frm.doc.status}`, {
                "Refunded": "green",
                "Pending": "yellow"
            }[frm.doc.status], "status-indicator");

        if (frm.doc.docstatus === 0) {
            // frm.page.clear_primary_action();

            frm.add_custom_button(__('Approve'), () => {
                frappe.confirm(
                    'Are you sure you want to approve this refund?',
                    () => {
                        frm.save('Submit');
                    },
                    () => {
                        // User cancelled the action
                    }
                );
            });

            frm.add_custom_button(__('Void'), () => {
                frappe.confirm(
                    'Are you sure you want to void the original payment?',
                    () => {
                        frappe.call({
                            method: 'metactical.metactical.doctype.usaepay_refund.usaepay_refund.void_useapay_payment',
                            freeze: true,
                            freeze_message: __('Voiding the original payment...'),
                            args: {
                                refund_name: frm.doc.name
                            },
                            callback: function (r) {
                                if (r.status === 'success') {
                                    frappe.msgprint(__('The original payment has been voided successfully.'));
                                } else {
                                    frappe.msgprint(__('Failed to void the original payment. '+ (r.message || '')));
                                }
                            }
                        });
                    },
                    () => {
                        // User cancelled the action
                    }
                );
            });
        }
    }
});
