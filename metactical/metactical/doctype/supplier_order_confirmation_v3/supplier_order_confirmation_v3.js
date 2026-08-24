// Copyright (c) 2026, Storebuilder Commerce Inc and contributors
// For license information, please see license.txt

// Migrated from Client Script "Supplier Order Confirmation V3 Form" (Form view).

function soc3_maybe_autopull(frm) {
    if (frm._soc3_autopull) return;
    if (!frm.is_new() || !frm.doc.purchase_order_v3) return;
    if ((frm.doc.items || []).some(function(d) { return d.item_code; })) return;
    frm._soc3_autopull = true;
    soc3_guard(frm, function() { soc3_fetch_lines(frm); });
}

function soc3_guard(frm, then) {
    if (!frm.doc.purchase_order_v3 || frm.doc.supersedes) { then(); return; }
    frappe.call({
        method: 'frappe.client.get_list',
        args: {
            doctype: 'Supplier Order Confirmation V3',
            filters: { purchase_order_v3: frm.doc.purchase_order_v3,
                       name: ['!=', frm.doc.name || ''], docstatus: ['<', 2] },
            fields: ['name'], limit_page_length: 1
        },
        callback: function(r) {
            var existing = (r.message || [])[0];
            if (!existing) { then(); return; }
            frappe.msgprint({
                title: __('Already confirmed'),
                indicator: 'orange',
                message: __('{0} is already confirmed on {1}.<br><br>Track back-order balances on its Back Orders section and attach later supplier documents on its Documents tab — no second confirmation is needed.',
                            [frm.doc.purchase_order_v3,
                             '<b><a href="/app/supplier-order-confirmation-v3/' + existing.name + '">'
                             + existing.name + '</a></b>']),
                primary_action: {
                    label: __('Open {0}', [existing.name]),
                    action: function() {
                        frappe.msg_dialog.hide();
                        frappe.set_route('Form', 'Supplier Order Confirmation V3', existing.name);
                    }
                }
            });
        }
    });
}

function soc3_fetch_lines(frm) {
    if (!frm.doc.purchase_order_v3) return;
    if ((frm.doc.items || []).some(function(d) { return d.item_code; })) return;
    frappe.call({
        method: 'frappe.client.get',
        args: { doctype: 'Purchase Order V3', name: frm.doc.purchase_order_v3 },
        callback: function(res) {
            var po = res.message; if (!po) return;
            frappe.call({
                method: 'frappe.client.get_list',
                args: {
                    doctype: 'Supplier Order Confirmation V3',
                    filters: { purchase_order_v3: po.name, name: ['!=', frm.doc.name || ''], docstatus: ['<', 2] },
                    fields: ['name'], limit_page_length: 0
                },
                callback: function(r2) {
                    var socs = (r2.message || []).map(function(s) { return s.name; });
                    if (!socs.length) { soc3_pull(frm, po, {}); return; }
                    frappe.call({
                        method: 'frappe.client.get_list',
                        args: {
                            doctype: 'Supplier Order Confirmation V3 Item',
                            filters: { parent: ['in', socs] },
                            fields: ['po3_item'], parent: 'Supplier Order Confirmation V3', limit_page_length: 0
                        },
                        callback: function(r3) {
                            var claimed = {};
                            (r3.message || []).forEach(function(x) { claimed[x.po3_item] = 1; });
                            soc3_pull(frm, po, claimed);
                        }
                    });
                }
            });
        }
    });
}

function soc3_pull(frm, po, claimed) {
    var TERMINAL = ['Received', 'Closed Short', 'Cancelled', 'Supplier Stock Out', 'Discontinued'];
    frm.clear_table('items');
    var skipped = 0;
    (po.items || []).forEach(function(r) {
        if (TERMINAL.indexOf(r.line_status) !== -1) { skipped++; return; }
        if (claimed[r.name] && r.line_status !== 'Back-ordered') { skipped++; return; }
        var d = frm.add_child('items');
        d.po3_item = r.name;
        d.item_code = r.item_code;
        d.retail_sku_suffix = r.retail_sku_suffix;
        d.ordered_qty = flt(r.qty) - flt(r.received_qty);
        d.confirmed_qty = d.ordered_qty;
        d.line_status = 'Confirmed';
        d.confirmed_rate = r.rate;
    });
    frm.refresh_field('items');
    var n = (frm.doc.items || []).length;
    frappe.show_alert({
        message: n ? __('Pulled {0} outstanding line(s){1}', [n, skipped ? __(' — {0} already handled', [skipped]) : ''])
                   : __('Nothing outstanding on {0}', [po.name]),
        indicator: n ? 'green' : 'orange'
    });
}

function soc3_export(frm) {
    var rows = [['item_code', 'item_name', 'retail_sku', 'supplier_sku', 'ordered_qty',
                 'confirmed_qty', 'line_status', 'backorder_eta', 'remarks']];
    (frm.doc.items || []).forEach(function(d) {
        rows.push([d.item_code, (d.item_name || '').replace(/"/g, "'"),
                   d.retail_sku_suffix || '', d.supplier_part_no || '',
                   flt(d.ordered_qty), flt(d.confirmed_qty), d.line_status || '',
                   d.backorder_eta || '', (d.remarks || '').replace(/"/g, "'")]);
    });
    var csv = rows.map(function(r) {
        return r.map(function(c) { return '"' + String(c) + '"'; }).join(',');
    }).join('\n');
    var blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = frm.doc.name + '_lines.csv';
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
}

function soc3_split(line, sep) {
    if (sep === '	') return line.split('	');
    var out = [], cur = '', inQ = false;
    for (var i = 0; i < line.length; i++) {
        var ch = line[i];
        if (ch === '"') {
            if (inQ && line[i + 1] === '"') { cur += '"'; i++; }
            else inQ = !inQ;
        } else if (ch === ',' && !inQ) { out.push(cur); cur = ''; }
        else cur += ch;
    }
    out.push(cur);
    return out;
}

function soc3_import(frm) {
    if (!(frm.doc.items || []).length) {
        frappe.msgprint(__('Pull the lines in first, then paste their statuses.'));
        return;
    }
    var d = new frappe.ui.Dialog({
        title: __('Paste line status from Excel'),
        size: 'large',
        fields: [
            { fieldtype: 'HTML', options:
              '<p style="margin-bottom:8px">Paste straight from Excel (tab separated) or a CSV, '
              + '<b>including the header row</b>. Recognised columns: '
              + '<code>item_code</code>, <code>retail_sku</code>, <code>confirmed_qty</code>, '
              + '<code>line_status</code>, <code>backorder_eta</code>, <code>confirmed_rate</code>, '
              + '<code>remarks</code>.<br>Rows are matched on item code or retail SKU. '
              + 'Only lines already on this confirmation are touched — nothing is added or removed.</p>' },
            { fieldtype: 'Small Text', fieldname: 'data', label: __('Pasted rows'), reqd: 1 }
        ],
        primary_action_label: __('Apply'),
        primary_action: function(v) {
            var lines = (v.data || '').split(/\r?\n/).filter(function(l) { return l.trim(); });
            if (!lines.length) return;
            var sep = lines[0].indexOf('\t') !== -1 ? '\t' : ',';
            var clean = function(x) { return String(x == null ? '' : x).trim().replace(/^"|"$/g, ''); };
            var hdr = soc3_split(lines[0], sep).map(function(h) { return clean(h).toLowerCase(); });
            if (hdr.indexOf('item_code') === -1 && hdr.indexOf('retail_sku') === -1) {
                frappe.msgprint(__('The first row must be a header containing item_code or retail_sku.'));
                return;
            }

            // index the grid rows by both identifiers
            var byKey = {};
            (frm.doc.items || []).forEach(function(row) {
                if (row.item_code) byKey[String(row.item_code).toUpperCase()] = row;
                if (row.retail_sku_suffix) byKey[String(row.retail_sku_suffix).toUpperCase()] = row;
            });

            var applied = 0, unknown = [], badStatus = [];
            var VALID = (frappe.meta.get_docfield('Supplier Order Confirmation V3 Item',
                'line_status', frm.doc.name) || {}).options || '';
            VALID = VALID.split('\n').filter(function(x) { return x; });

            lines.slice(1).forEach(function(l) {
                var cells = soc3_split(l, sep).map(clean);
                var rec = {};
                hdr.forEach(function(h, i) { if (cells[i] !== undefined && cells[i] !== '') rec[h] = cells[i]; });
                var key = (rec.item_code || rec.retail_sku || '').toUpperCase();
                if (!key) return;
                var row = byKey[key];
                if (!row) { unknown.push(rec.item_code || rec.retail_sku); return; }
                if (rec.line_status) {
                    if (VALID.length && VALID.indexOf(rec.line_status) === -1) {
                        badStatus.push(rec.line_status);
                    } else {
                        frappe.model.set_value(row.doctype, row.name, 'line_status', rec.line_status);
                    }
                }
                if (rec.confirmed_qty !== undefined) {
                    frappe.model.set_value(row.doctype, row.name, 'confirmed_qty', flt(rec.confirmed_qty));
                }
                if (rec.backorder_eta) {
                    frappe.model.set_value(row.doctype, row.name, 'backorder_eta', rec.backorder_eta);
                }
                if (rec.confirmed_rate !== undefined) {
                    frappe.model.set_value(row.doctype, row.name, 'confirmed_rate', flt(rec.confirmed_rate));
                }
                if (rec.remarks !== undefined) {
                    frappe.model.set_value(row.doctype, row.name, 'remarks', rec.remarks);
                }
                applied++;
            });

            d.hide();
            frm.refresh_field('items');

            var msg = __('Updated {0} of {1} line(s). Review, then Save.',
                         [applied, (frm.doc.items || []).length]);
            if (unknown.length) {
                msg += '<br><br><b>' + __('Not on this confirmation ({0}):', [unknown.length]) + '</b> '
                     + unknown.slice(0, 25).join(', ') + (unknown.length > 25 ? ' …' : '');
            }
            if (badStatus.length) {
                var uniq = badStatus.filter(function(x, i) { return badStatus.indexOf(x) === i; });
                msg += '<br><br><b>' + __('Unrecognised line status, left unchanged:') + '</b> '
                     + uniq.join(', ') + '<br><i>' + __('Valid:') + '</i> ' + VALID.join(' · ');
            }
            frappe.msgprint({ title: __('Paste applied'), message: msg, indicator: applied ? 'green' : 'orange' });
        }
    });
    d.show();
}

frappe.ui.form.on('Supplier Order Confirmation V3', {
    purchase_order_v3: function(frm) {
        frm._soc3_autopull = true;
        soc3_guard(frm, function() { soc3_fetch_lines(frm); });
    },
    onload_post_render: function(frm) { soc3_maybe_autopull(frm); },
    refresh: function(frm) {
        soc3_maybe_autopull(frm);
        // Top-level, ungrouped: a dropdown group made these easy to miss.
        if (frm.doc.docstatus === 0) {
            frm.add_custom_button(__('⭳ Download Lines'), function() { soc3_export(frm); })
                .removeClass('btn-default');
            frm.add_custom_button(__('⭱ Paste Line Status'), function() { soc3_import(frm); })
                .removeClass('btn-default');
            if (frm.doc.purchase_order_v3) {
                frm.add_custom_button(__('Fetch Outstanding Lines'), function() {
                    frm.clear_table('items'); frm.refresh_field('items'); soc3_fetch_lines(frm);
                });
            }
        } else if ((frm.doc.items || []).length) {
            frm.add_custom_button(__('⭳ Download Lines'), function() { soc3_export(frm); });
        }
        if (frm.doc.purchase_order_v3) {
            frm.add_custom_button(__('Purchase Order V3'), function() {
                frappe.set_route('Form', 'Purchase Order V3', frm.doc.purchase_order_v3);
            }, __('View'));
        }
        // Same actions on the Lines grid, where an operator is actually working.
        if (frm.fields_dict.items && frm.fields_dict.items.grid) {
            var grid = frm.fields_dict.items.grid;
            if (!grid._v3_buttons) {
                grid._v3_buttons = true;
                grid.add_custom_button(__('⭳ Download'), function() { soc3_export(frm); });
                if (frm.doc.docstatus === 0) {
                    grid.add_custom_button(__('⭱ Paste Status'), function() { soc3_import(frm); });
                }
            }
        }
    }
});

// ---------------------------------------------------------------------------
// Migrated from Client Script "Supplier Order Confirmation V3 Stale State Guard"
// (Form view). Refuses a workflow action when the document has already moved on
// in the DB, so the user re-picks from the refreshed action list.
// ---------------------------------------------------------------------------

frappe.ui.form.on('Supplier Order Confirmation V3', {
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