// Copyright (c) 2026, Storebuilder Commerce Inc and contributors
// For license information, please see license.txt

// Migrated from Client Script "Supplier Claim V3 Stale State Guard" (Form view).
// Refuses a workflow action when the document has already moved on in the DB,
// so the user re-picks from the refreshed action list.

frappe.ui.form.on('Supplier Claim V3', {
    before_workflow_action: function(frm) {
        return new Promise(function(resolve, reject) {
            if (frm.is_new() || !frm.doc.name) { resolve(); return; }
            frappe.db.get_value(frm.doctype, frm.doc.name, 'workflow_state')
                .then(function(r) {
                    var server = (r && r.message) ? r.message.workflow_state : null;
                    if (!server || server === frm.doc.workflow_state) { resolve(); return; }
                    frm.reload_doc().then(function() {
                        frappe.show_alert({
                            message: __('This document had already moved to <b>{0}</b>. Refreshed — pick the action you want from the updated list.', [server]),
                            indicator: 'orange'
                        }, 10);
                    });
                    reject();
                })
                .catch(function() { resolve(); });   // never block on a lookup failure
        });
    }
});
// Create > Purchase Return: a draft native Purchase Receipt (Is Return) for the
// claimed goods - see make_purchase_return.
frappe.ui.form.on('Supplier Claim V3', {
    refresh: function(frm) {
        if (frm.is_new()) return;
        frm.add_custom_button(__('Purchase Return'), function() {
            frappe.call({
                method: 'metactical.metactical.doctype.supplier_claim_v3.supplier_claim_v3.make_purchase_return',
                args: { claim: frm.doc.name },
                freeze: true,
                freeze_message: __('Creating Purchase Return...'),
                callback: function(r) {
                    var m = r.message || {};
                    var links = (m.returns || []).map(function(n) {
                        return '<a href="/app/purchase-receipt/' + n + '">' + n + '</a>';
                    });
                    var msg = __('Draft Purchase Return created: {0}. Review and submit it.', [links.join(', ')]);
                    if ((m.skipped || []).length) {
                        msg += '<br><br><b>' + __('Not returned:') + '</b><br>' + m.skipped.join('<br>');
                    }
                    frappe.msgprint({ title: __('Purchase Return'), message: msg, indicator: 'green' });
                    frm.reload_doc();
                }
            });
        }, __('Create'));
    }
});
