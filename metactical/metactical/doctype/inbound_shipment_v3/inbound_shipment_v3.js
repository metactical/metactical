// Copyright (c) 2026, Storebuilder Commerce Inc and contributors
// For license information, please see license.txt

// Migrated from Client Script "Inbound Shipment V3 Form" (Form view).

// Only suppliers flagged is_transporter are carriers, and a carrier's
// services are its own - picking UPS must not offer FedEx Ground.
function ins3_carrier_queries(frm) {
    frm.set_query('carrier', function () {
        return { filters: { is_transporter: 1, disabled: 0 } };
    });
    frm.set_query('carrier', 'boxes', function () {
        return { filters: { is_transporter: 1, disabled: 0 } };
    });
    frm.set_query('carrier_service', function () {
        return { filters: { carrier: frm.doc.carrier || '', disabled: 0 } };
    });
    frm.set_query('carrier_service', 'boxes', function (doc, cdt, cdn) {
        var row = locals[cdt][cdn];
        return { filters: { carrier: row.carrier || frm.doc.carrier || '', disabled: 0 } };
    });
}

function ins3_fetch(frm) {
    if (!frm.doc.purchase_order_v3) return;
    if ((frm.doc.items || []).some(function(d) { return d.item_code; })) return;
    frappe.call({
        method: 'frappe.client.get_list',
        args: { doctype: 'Supplier Order Confirmation V3',
                filters: { purchase_order_v3: frm.doc.purchase_order_v3, docstatus: ['<', 2] },
                fields: ['name'], limit_page_length: 1 },
        callback: function(r) {
            var socName = (r.message || [])[0] ? r.message[0].name : null;
            if (socName && !frm.doc.supplier_order_confirmation_v3) {
                frm.set_value('supplier_order_confirmation_v3', socName);
            }
            var after = function(promised, notComing) {
                frappe.db.get_doc('Purchase Order V3', frm.doc.purchase_order_v3).then(function(po) {
                    frm.clear_table('items');
                    var skipped = 0;
                    (po.items || []).forEach(function(r) {
                        if (['Received','Closed Short','Cancelled','Supplier Stock Out','Discontinued'].indexOf(r.line_status) !== -1) { skipped++; return; }
                        if (notComing[r.name]) { skipped++; return; }
                        var p = promised[r.name];
                        var shipped = flt(r.shipped_qty);
                        var split = (r.line_status === 'Back-ordered') ||
                            (p && ['Back-ordered','Partial - Balance Back-ordered'].indexOf(p.line_status) !== -1);
                        var base;
                        if (p && split) { base = (shipped < flt(p.confirmed_qty)) ? flt(p.confirmed_qty) : flt(r.qty); }
                        else if (p) { base = flt(p.confirmed_qty); }
                        else { base = flt(r.qty); }
                        var out = base - flt(r.shipped_qty);
                        if (out <= 0) { skipped++; return; }
                        var d = frm.add_child('items');
                        d.po3_item = r.name;
                        d.item_code = r.item_code;
                        d.qty = out;
                    });
                    frm.refresh_field('items');
                    var n = (frm.doc.items || []).length;
                    frappe.show_alert({
                        message: n ? __('Pulled {0} expected line(s){1}', [n, socName ? __(' from confirmation {0}', [socName]) : ''])
                                   : __('Nothing outstanding to ship'),
                        indicator: n ? 'green' : 'orange' }, 7);
                });
            };
            if (!socName) { after({}, {}); return; }
            frappe.call({
                method: 'frappe.client.get_list',
                args: { doctype: 'Supplier Order Confirmation V3 Item', parent: 'Supplier Order Confirmation V3',
                        filters: { parent: socName }, fields: ['po3_item','confirmed_qty','line_status'],
                        limit_page_length: 0 },
                callback: function(r2) {
                    var promised = {}, notComing = {};
                    (r2.message || []).forEach(function(l) {
                        promised[l.po3_item] = l;
                        if (['Supplier Stock Out','Discontinued','Cancelled by Supplier'].indexOf(l.line_status) !== -1)
                            notComing[l.po3_item] = 1;
                    });
                    after(promised, notComing);
                }
            });
        }
    });
}

frappe.ui.form.on('Inbound Shipment V3', {
    onload: function (frm) { ins3_carrier_queries(frm); },
    carrier: function (frm) {
        // changing the carrier invalidates a service belonging to the old one
        if (frm.doc.carrier_service) frm.set_value('carrier_service', null);
    },

    purchase_order_v3: ins3_fetch,
    onload_post_render: function(frm) { if (frm.is_new()) ins3_fetch(frm); },
    refresh: function(frm) {
        if (frm.doc.docstatus === 0 && frm.doc.purchase_order_v3) {
            frm.add_custom_button(__('Fetch Expected Lines'), function() {
                frm.clear_table('items'); frm.refresh_field('items'); ins3_fetch(frm);
            });
        }
        if (frm.doc.supplier_order_confirmation_v3) {
            frm.add_custom_button(__('Confirmation'), function() {
                frappe.set_route('Form','Supplier Order Confirmation V3', frm.doc.supplier_order_confirmation_v3);
            }, __('View'));
        }
        if (frm.doc.purchase_order_v3) {
            frm.add_custom_button(__('Purchase Order V3'), function() {
                frappe.set_route('Form','Purchase Order V3', frm.doc.purchase_order_v3);
            }, __('View'));
        }
    }
});

frappe.ui.form.on('Inbound Shipment V3 Box', {
    carrier: function (frm, cdt, cdn) {
        frappe.model.set_value(cdt, cdn, 'carrier_service', null);
    }
});

// ---------------------------------------------------------------------------
// Migrated from Client Script "Inbound Shipment V3 Stale State Guard" (Form view).
// Refuses a workflow action when the document has already moved on in the DB.
// Especially relevant here: posting a Goods Receipt V3 can flip this shipment to
// Received server-side, so an open form can easily be looking at a stale state.
// ---------------------------------------------------------------------------

frappe.ui.form.on('Inbound Shipment V3', {
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