// Copyright (c) 2026, Storebuilder Commerce Inc and contributors
// For license information, please see license.txt

frappe.ui.form.on("USAePay Refund", {
	refresh(frm) {
        if (frm.doc.docstatus === 0) {
            frm.page.clear_primary_action();

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
        }
    }
});
