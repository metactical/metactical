// Copyright (c) 2026, Storebuilder Commerce Inc and contributors
// For license information, please see license.txt

// Migrated from Client Script "Supplier Order Confirmation V3 Form" (Form view).

// Line statuses where nothing ships now, so Confirmed Qty is 0. Mirrors
// ZERO_QTY_STATUSES in the controller, which enforces the same on save.
var SOC3_ZERO_QTY_STATUSES = ['Back-ordered', 'Supplier Stock Out', 'Discontinued', 'Cancelled by Supplier'];

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
        d.item_name = r.item_name;
        d.retail_sku_suffix = r.retail_sku_suffix;
        // the supplier's own identifiers come straight off the order line, so
        // they read back during keying instead of appearing only after a save
        d.supplier_part_no = r.supplier_part_no;
        d.barcode = r.barcode;
        d.ordered_qty = flt(r.qty) - flt(r.received_qty);
        d.confirmed_qty = d.ordered_qty;
        d.line_status = 'Confirmed';
        d.confirmed_rate = r.rate;
    });
    frm.refresh_field('items');
    soc3_copy_taxes(frm, po);
    soc3_totals(frm);
    soc3_calc_taxes(frm);
    soc3_fill_blanks(frm);
    var n = (frm.doc.items || []).length;
    frappe.show_alert({
        message: n ? __('Pulled {0} outstanding line(s){1}', [n, skipped ? __(' — {0} already handled', [skipped]) : ''])
                   : __('Nothing outstanding on {0}', [po.name]),
        indicator: n ? 'green' : 'orange'
    });
}

// The order's taxes and discount, for the supplier's confirmation to start
// from. Assigned rather than set_value so taxes_and_charges does not fire and
// replace the order's rows with the template's. Amounts are redone on save.
var SOC3_TAX_SETTINGS = ['tax_category', 'taxes_and_charges', 'apply_discount_on',
    'additional_discount_percentage', 'discount_amount', 'disable_rounded_total'];
var SOC3_ROW_SKIP = ['name', 'parent', 'parenttype', 'parentfield', 'idx', 'doctype', 'owner',
    'creation', 'modified', 'modified_by', 'docstatus'];

function soc3_copy_taxes(frm, po) {
    if ((frm.doc.taxes || []).length) return;
    SOC3_TAX_SETTINGS.forEach(function(f) {
        frm.doc[f] = po[f];
        frm.refresh_field(f);
    });
    (po.taxes || []).forEach(function(t) {
        var row = frm.add_child('taxes');
        Object.keys(t).forEach(function(k) {
            if (SOC3_ROW_SKIP.indexOf(k) === -1 && k.indexOf('__') !== 0) row[k] = t[k];
        });
    });
    frm.refresh_field('taxes');
}

// Header totals, mirroring set_totals() in the controller so the numbers move
// while the confirmation is being keyed in, before anything has been saved.
function soc3_totals(frm) {
    var ordered = 0, confirmed = 0, amount = 0;
    (frm.doc.items || []).forEach(function(d) {
        ordered += flt(d.ordered_qty);
        confirmed += flt(d.confirmed_qty);
        amount += flt(d.confirmed_qty) * flt(d.confirmed_rate);
    });
    // the back-order rows are rebuilt server-side on save, so before the first
    // save the balance has to be read off the lines themselves
    var back = 0;
    (frm.doc.items || []).forEach(function(d) {
        if (d.line_status === 'Back-ordered') back += flt(d.ordered_qty);
        else if (d.line_status === 'Partial - Balance Back-ordered') {
            back += Math.max(flt(d.ordered_qty) - flt(d.confirmed_qty), 0);
        }
    });

    // assigned rather than set_value: these are display copies of what the
    // controller recomputes on save, and set_value would mark an untouched
    // document dirty every time it is opened
    frm.doc.total_ordered_qty = ordered;
    frm.doc.total_qty = confirmed;
    frm.doc.total_backorder_qty = back;
    frm.doc.total = amount;
    frm.doc.base_total = amount * (flt(frm.doc.conversion_rate) || 1);
    ['total_ordered_qty', 'total_qty', 'total_backorder_qty', 'total', 'base_total']
        .forEach(function(f) { frm.refresh_field(f); });
}

// Server-side details for every grid line, in grid order. A pulled confirmation
// that has not been saved yet only has what its PO3 lines carried.
function soc3_line_details(frm, then) {
    var items = frm.doc.items || [];
    if (!items.length) { then([]); return; }
    frappe.call({
        method: 'metactical.metactical.doctype.supplier_order_confirmation_v3'
              + '.supplier_order_confirmation_v3.line_details',
        args: {
            lines: items.map(function(d) { return { item_code: d.item_code, po3_item: d.po3_item }; }),
            supplier: frm.doc.supplier
        },
        callback: function(r) { then(r.message || []); }
    });
}

// Fill whatever a pull left blank. Assigned rather than set_value, like the
// totals: these are display copies the controller rewrites on save anyway.
function soc3_fill_blanks(frm) {
    soc3_line_details(frm, function(details) {
        (frm.doc.items || []).forEach(function(d, i) {
            var x = details[i] || {};
            ['item_name', 'retail_sku_suffix', 'barcode', 'supplier_part_no'].forEach(function(f) {
                if (!d[f] && x[f]) d[f] = x[f];
            });
        });
        frm.refresh_field('items');
    });
}

function soc3_export(frm) {
    soc3_line_details(frm, function(details) {
        var rows = [['item_code', 'item_name', 'retail_sku', 'supplier_sku', 'barcode', 'ordered_qty',
                     'confirmed_qty', 'confirmed_rate', 'line_status', 'backorder_eta', 'remarks']];
        (frm.doc.items || []).forEach(function(d, i) {
            var x = details[i] || {};
            rows.push([d.item_code || '', d.item_name || x.item_name || '',
                       d.retail_sku_suffix || x.retail_sku_suffix || '',
                       d.supplier_part_no || x.supplier_part_no || '',
                       d.barcode || x.barcode || '',
                       flt(d.ordered_qty), flt(d.confirmed_qty),
                       // no rate given = the order price, as on save
                       flt(d.confirmed_rate) || flt(x.po3_rate),
                       d.line_status || '', d.backorder_eta || (d.eta_tbd ? 'TBD' : ''), d.remarks || '']);
        });
        // quotes doubled per CSV rules; the barcode's leading zeros survive in
        // the file, though Excel may still show it as a number when opened
        var csv = rows.map(function(r) {
            return r.map(function(c) { return '"' + String(c).replace(/"/g, '""') + '"'; }).join(',');
        }).join('\n');
        var blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
        var a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = (frm.doc.name || 'confirmation') + '_lines.csv';
        document.body.appendChild(a); a.click(); document.body.removeChild(a);
    });
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
              + '<code>item_code</code>, <code>retail_sku</code>, <code>barcode</code>, <code>confirmed_qty</code>, '
              + '<code>line_status</code>, <code>backorder_eta</code> (a date, or TBD), <code>confirmed_rate</code>, '
              + '<code>remarks</code>.<br>Rows are matched on item code, retail SKU or barcode. '
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
            if (hdr.indexOf('item_code') === -1 && hdr.indexOf('retail_sku') === -1
                    && hdr.indexOf('barcode') === -1) {
                frappe.msgprint(__('The first row must be a header containing item_code, retail_sku or barcode.'));
                return;
            }

            // index the grid rows by both identifiers
            var byKey = {};
            (frm.doc.items || []).forEach(function(row) {
                if (row.item_code) byKey[String(row.item_code).toUpperCase()] = row;
                if (row.retail_sku_suffix) byKey[String(row.retail_sku_suffix).toUpperCase()] = row;
                if (row.barcode) byKey[String(row.barcode).toUpperCase()] = row;
            });

            var applied = 0, unknown = [], badStatus = [];
            var VALID = (frappe.meta.get_docfield('Supplier Order Confirmation V3 Item',
                'line_status', frm.doc.name) || {}).options || '';
            VALID = VALID.split('\n').filter(function(x) { return x; });

            lines.slice(1).forEach(function(l) {
                var cells = soc3_split(l, sep).map(clean);
                var rec = {};
                hdr.forEach(function(h, i) { if (cells[i] !== undefined && cells[i] !== '') rec[h] = cells[i]; });
                var key = (rec.item_code || rec.retail_sku || rec.barcode || '').toUpperCase();
                if (!key) return;
                var row = byKey[key];
                if (!row) { unknown.push(rec.item_code || rec.retail_sku || rec.barcode); return; }
                if (rec.line_status) {
                    if (VALID.length && VALID.indexOf(rec.line_status) === -1) {
                        badStatus.push(rec.line_status);
                    } else {
                        frappe.model.set_value(row.doctype, row.name, 'line_status', rec.line_status);
                    }
                }
                // a nothing-ships status wins over a pasted quantity, as on save
                if (SOC3_ZERO_QTY_STATUSES.indexOf(row.line_status) !== -1
                        || SOC3_ZERO_QTY_STATUSES.indexOf(rec.line_status) !== -1) {
                    frappe.model.set_value(row.doctype, row.name, 'confirmed_qty', 0);
                } else if (rec.confirmed_qty !== undefined) {
                    frappe.model.set_value(row.doctype, row.name, 'confirmed_qty', flt(rec.confirmed_qty));
                } else if (rec.line_status === 'Confirmed') {
                    frappe.model.set_value(row.doctype, row.name, 'confirmed_qty', flt(row.ordered_qty));
                }
                if (String(rec.backorder_eta || '').toUpperCase() === 'TBD') {
                    frappe.model.set_value(row.doctype, row.name, 'backorder_eta', null);
                    frappe.model.set_value(row.doctype, row.name, 'eta_tbd', 1);
                } else if (rec.backorder_eta) {
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
            soc3_totals(frm);

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

frappe.ui.form.on('Supplier Order Confirmation V3 Item', {
    confirmed_qty: function(frm) { soc3_totals(frm); },
    confirmed_rate: function(frm) { soc3_totals(frm); },
    line_status: function(frm, cdt, cdn) {
        var row = locals[cdt][cdn];
        // confirmed_qty's own handler recomputes the totals
        if (SOC3_ZERO_QTY_STATUSES.indexOf(row.line_status) !== -1 && flt(row.confirmed_qty) !== 0) {
            frappe.model.set_value(cdt, cdn, 'confirmed_qty', 0);
        } else if (row.line_status === 'Confirmed' && flt(row.confirmed_qty) !== flt(row.ordered_qty)) {
            // Confirmed always means the full outstanding qty
            frappe.model.set_value(cdt, cdn, 'confirmed_qty', flt(row.ordered_qty));
        } else {
            soc3_totals(frm);
        }
    },
    items_remove: function(frm) { soc3_totals(frm); },
    // a date and "to be determined" exclude each other
    backorder_eta: function(frm, cdt, cdn) {
        if (locals[cdt][cdn].backorder_eta && locals[cdt][cdn].eta_tbd) {
            frappe.model.set_value(cdt, cdn, 'eta_tbd', 0);
        }
    },
    eta_tbd: function(frm, cdt, cdn) {
        if (locals[cdt][cdn].eta_tbd && locals[cdt][cdn].backorder_eta) {
            frappe.model.set_value(cdt, cdn, 'backorder_eta', null);
        }
    },
    item_code: function(frm, cdt, cdn) {
        var row = locals[cdt][cdn];
        if (!row.item_code) return;
        frappe.call({
            method: 'metactical.metactical.doctype.supplier_order_confirmation_v3'
                  + '.supplier_order_confirmation_v3.item_identifiers',
            args: { item_code: row.item_code, supplier: frm.doc.supplier },
            callback: function(r) {
                var ii = r.message || {};
                frappe.model.set_value(cdt, cdn, 'item_name', ii.item_name);
                frappe.model.set_value(cdt, cdn, 'retail_sku_suffix', ii.retail_sku_suffix);
                frappe.model.set_value(cdt, cdn, 'barcode', ii.barcode);
                frappe.model.set_value(cdt, cdn, 'supplier_part_no', ii.supplier_part_no);
            }
        });
    }
});

frappe.ui.form.on('Supplier Order Confirmation V3', {
    purchase_order_v3: function(frm) {
        frm._soc3_autopull = true;
        soc3_guard(frm, function() { soc3_fetch_lines(frm); });
    },
    onload_post_render: function(frm) { soc3_maybe_autopull(frm); },
    refresh: function(frm) {
        soc3_maybe_autopull(frm);
        if (frm.doc.docstatus === 0) soc3_totals(frm);
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
        // The receipt is counted against this confirmation, so it can be raised
        // from here as it is from the PO3.
        if (frm.doc.docstatus === 1 && frm.doc.purchase_order_v3) {
            frm.add_custom_button(__('Purchase Receipt V3'), function() {
                frappe.model.with_doctype('Purchase Receipt V3', function() {
                    var doc = frappe.model.get_new_doc('Purchase Receipt V3');
                    doc.purchase_order_v3 = frm.doc.purchase_order_v3;
                    frappe.set_route('Form', 'Purchase Receipt V3', doc.name);
                });
            }, __('Create'));
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

// Taxes and Charges -- the native Purchase Order's own fields and child table.
// Totals, taxes and discount are worked out by ERPNext's own engine
// (metactical/procurement_v3/taxes.py): on save, and while the form is being
// keyed in through preview_totals, so they move as they do on the native PO.

// The native PO's own tax-grid behaviour: Rate editable and required, Amount
// read-only -- the other way round for "Actual" -- the account query and the
// row checks.
erpnext.accounts.taxes.setup_tax_validations('Supplier Order Confirmation V3');

var SOC3_TOTAL_FIELDS = ['total', 'base_total', 'net_total', 'base_net_total',
    'taxes_and_charges_added', 'base_taxes_and_charges_added',
    'taxes_and_charges_deducted', 'base_taxes_and_charges_deducted',
    'total_taxes_and_charges', 'base_total_taxes_and_charges',
    'discount_amount', 'base_discount_amount', 'grand_total', 'base_grand_total',
    'rounding_adjustment', 'base_rounding_adjustment', 'rounded_total', 'base_rounded_total'];

// Debounced: a burst of edits (a template's rows, a pasted status sheet) makes
// one call, and an answer to an older call is dropped.
function soc3_calc_taxes(frm) {
    if (frm.doc.docstatus !== 0) return;
    clearTimeout(frm._soc3_calc_timer);
    frm._soc3_calc_timer = setTimeout(function() {
        var seq = frm._soc3_calc_seq = (frm._soc3_calc_seq || 0) + 1;
        frappe.call({
            method: 'metactical.metactical.doctype.supplier_order_confirmation_v3'
                  + '.supplier_order_confirmation_v3.preview_totals',
            args: { doc: frm.doc },
            callback: function(r) {
                if (seq !== frm._soc3_calc_seq || !r.message) return;
                // assigned rather than set_value, like soc3_totals: display
                // copies of what save recomputes, and set_value would fire
                // these handlers again
                SOC3_TOTAL_FIELDS.forEach(function(f) {
                    if (f in r.message.totals) frm.doc[f] = r.message.totals[f];
                });
                (frm.doc.taxes || []).forEach(function(t, i) {
                    var calc = r.message.taxes[i] || {};
                    Object.keys(calc).forEach(function(f) {
                        // an Actual row's amount is what the user typed
                        if (f === 'tax_amount' && t.charge_type === 'Actual') return;
                        if (f === 'description' && t.description) return;
                        t[f] = calc[f];
                    });
                });
                (frm.doc.items || []).forEach(function(d, i) {
                    var calc = r.message.items[i] || {};
                    d.net_rate = calc.net_rate;
                    d.net_amount = calc.net_amount;
                });
                SOC3_TOTAL_FIELDS.forEach(function(f) { frm.refresh_field(f); });
                frm.refresh_field('taxes');
            }
        });
    }, 300);
}

frappe.ui.form.on('Supplier Order Confirmation V3', {
    setup: function(frm) {
        frm.set_query('taxes_and_charges', function() {
            return { filters: { company: frm.doc.company, disabled: 0 } };
        });
        // an item added to the order, or sent as a substitute, can't be a
        // discontinued or disabled one (validate refuses them)
        ['item_code', 'substitute_item_code'].forEach(function(f) {
            frm.set_query(f, 'items', function() {
                return { filters: { ifw_discontinued: 0, disabled: 0 } };
            });
        });
        frm.set_query('cost_center', 'taxes', function() {
            return { filters: { company: frm.doc.company, is_group: 0 } };
        });
    },
    taxes_and_charges: function(frm) {
        if (!frm.doc.taxes_and_charges) return;
        frappe.call({
            method: 'erpnext.controllers.accounts_controller.get_taxes_and_charges',
            args: { master_doctype: 'Purchase Taxes and Charges Template', master_name: frm.doc.taxes_and_charges },
            callback: function(r) {
                frm.clear_table('taxes');
                (r.message || []).forEach(function(t) { frm.add_child('taxes', t); });
                frm.refresh_field('taxes');
                soc3_calc_taxes(frm);
            }
        });
    },
    apply_discount_on: function(frm) { soc3_calc_taxes(frm); },
    additional_discount_percentage: function(frm) { soc3_calc_taxes(frm); },
    discount_amount: function(frm) { soc3_calc_taxes(frm); },
    disable_rounded_total: function(frm) { soc3_calc_taxes(frm); },
    taxes_remove: function(frm) { soc3_calc_taxes(frm); },
    // Description is mandatory on ERPNext's tax row, but picking the account
    // is all that is needed: fill it from the account, as the native PO does,
    // and let the row through either way -- save fills it too (prepare_tax_rows).
    validate: function(frm) { v3_tax_descriptions(frm); }
});

function v3_tax_descriptions(frm) {
    (frm.doc.taxes || []).forEach(function(t) {
        if (t.account_head && !t.description) {
            t.description = t.account_head.split(' - ').slice(0, -1).join(' - ') || t.account_head;
        }
        // this row's own copy of the field, so the native PO is unaffected
        var df = frappe.meta.get_docfield(t.doctype, 'description', t.name);
        if (df) df.reqd = 0;
    });
    frm.refresh_field('taxes');
}

// The same lines' changes that move soc3_totals move the taxes too.
frappe.ui.form.on('Supplier Order Confirmation V3 Item', {
    confirmed_qty: function(frm) { soc3_calc_taxes(frm); },
    confirmed_rate: function(frm) { soc3_calc_taxes(frm); },
    items_remove: function(frm) { soc3_calc_taxes(frm); }
});

// The tax row itself. Purchase Taxes and Charges is shared with the native PO
// and PO3, so these only act on a confirmation. Picking an account fills Rate
// and Description as the native PO does (erpnext accounts.js, account_head).
frappe.ui.form.on('Purchase Taxes and Charges', {
    account_head: function(frm, cdt, cdn) {
        if (frm.doctype !== 'Supplier Order Confirmation V3') return;
        var d = locals[cdt][cdn];
        if (d.docstatus == 1) return;
        if (!d.charge_type && d.account_head) {
            frappe.msgprint(__('Please select Charge Type first'));
            frappe.model.set_value(cdt, cdn, 'account_head', '');
        } else if (d.account_head) {
            frappe.call({
                type: 'GET',
                method: 'erpnext.controllers.accounts_controller.get_tax_rate',
                args: { account_head: d.account_head },
                callback: function(r) {
                    var acc = r.message || {};
                    if (d.charge_type !== 'Actual') {
                        frappe.model.set_value(cdt, cdn, 'rate', acc.tax_rate || 0);
                    }
                    frappe.model.set_value(cdt, cdn, 'description', acc.account_name);
                    soc3_calc_taxes(frm);
                }
            });
        }
    },
    charge_type: function(frm, cdt, cdn) {
        if (frm.doctype !== 'Supplier Order Confirmation V3') return;
        erpnext.accounts.taxes.validate_taxes_and_charges(cdt, cdn);
        var row = frm.open_grid_row() || frm.get_field('taxes').grid.get_row(cdn);
        erpnext.accounts.taxes.set_conditional_mandatory_rate_or_amount(row);
        soc3_calc_taxes(frm);
    },
    rate: function(frm, cdt, cdn) {
        if (frm.doctype !== 'Supplier Order Confirmation V3') return;
        erpnext.accounts.taxes.validate_taxes_and_charges(cdt, cdn);
        soc3_calc_taxes(frm);
    },
    tax_amount: function(frm, cdt, cdn) {
        if (frm.doctype !== 'Supplier Order Confirmation V3') return;
        erpnext.accounts.taxes.validate_taxes_and_charges(cdt, cdn);
        soc3_calc_taxes(frm);
    },
    row_id: function(frm, cdt, cdn) {
        if (frm.doctype !== 'Supplier Order Confirmation V3') return;
        erpnext.accounts.taxes.validate_taxes_and_charges(cdt, cdn);
        soc3_calc_taxes(frm);
    },
    add_deduct_tax: function(frm) {
        if (frm.doctype === 'Supplier Order Confirmation V3') soc3_calc_taxes(frm);
    },
    category: function(frm) {
        if (frm.doctype === 'Supplier Order Confirmation V3') soc3_calc_taxes(frm);
    },
    included_in_print_rate: function(frm) {
        if (frm.doctype === 'Supplier Order Confirmation V3') soc3_calc_taxes(frm);
    }
});
