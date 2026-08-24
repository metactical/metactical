// Copyright (c) 2026, Storebuilder Commerce Inc and contributors
// For license information, please see license.txt

// Migrated from Client Script "Goods Receipt V3 Form" (Form view).
//
// Depends on these Server Script APIs (still DB-resident, migrated later):
//   v3_gr3_scan_map, v3_gr3_prefill_preview, v3_retry_gr3_posting

function gr3_undo_last_scan(frm) {
    var st = frm._scan_undo || [];
    if (!st.length) { frappe.show_alert({ message: __('Nothing to undo'), indicator: 'orange' }, 3); return; }
    var u = st.pop();
    var row = (frm.doc.items || []).find(function (d) { return d.name === u.row; });
    if (!row) { frappe.show_alert({ message: __('That line is gone'), indicator: 'orange' }, 3); return; }
    if (u.added) {
        frm.get_field('items').grid.grid_rows_by_docname[u.row].remove();
    } else {
        row.received_qty = u.was;
        row.accepted_qty = flt(row.received_qty) - flt(row.rejected_qty);
    }
    frm.refresh_field('items');
    frm.dirty();
    gr3_scan_feedback(frm, true, __('Undone') + ': ' + u.label + ' \u2212' + u.step);
}

// Counting from zero is right, but it must not mean typing 200 lines by hand
// when the delivery is clean. These set the count to what was expected.
function gr3_count_rows(frm, rows, mode) {
    var n = 0;
    rows.forEach(function (d) {
        var v = (mode === 'zero') ? 0 : flt(d.expected_qty);
        if (flt(d.received_qty) === v) return;
        frm._scan_undo = frm._scan_undo || [];
        frm._scan_undo.push({ row: d.name, was: flt(d.received_qty), added: false,
            label: d.received_item_code || '?', step: v - flt(d.received_qty) });
        d.received_qty = v;
        d.accepted_qty = v - flt(d.rejected_qty);
        n++;
    });
    frm.refresh_field('items');
    if (n) frm.dirty();
    frappe.show_alert({ message: n + __(' lines updated'), indicator: n ? 'green' : 'orange' }, 3);
}

function gr3_selected_rows(frm) {
    var sel = frm.get_field('items').grid.get_selected_children();
    return (sel && sel.length) ? sel : [];
}

function gr3_bind_scan_enter(frm) {
    var f = frm.get_field('scan_barcode');
    if (!f || !f.$input) return;
    f.$input.off('keydown.gr3').on('keydown.gr3', function (e) {
        if (e.which !== 13) return;          // scanners send Enter; so do people
        e.preventDefault();
        e.stopPropagation();
        var v = this.value;
        gr3_handle_scan(frm, v);
        var me = this;
        setTimeout(function () { me.value = ''; me.focus(); }, 40);
    });
}

function clm3_new_from(field, value) {
    frappe.model.with_doctype('Supplier Claim V3', function () {
        var d = frappe.model.get_new_doc('Supplier Claim V3');
        d[field] = value;
        d.claim_date = frappe.datetime.get_today();
        frappe.set_route('Form', 'Supplier Claim V3', d.name);
    });
}

// ---- Scan to Count -------------------------------------------------
// The map is fetched once per order, so each scan is instant - no round
// trip. An unknown code falls back to a server lookup, which is rare
// enough that the latency does not matter.
function gr3_load_scan_map(frm) {
    if (!frm.doc.purchase_order_v3) { frm._scan = null; return; }
    if (frm._scan && frm._scan.po === frm.doc.purchase_order_v3) return;
    frappe.call({
        method: 'v3_gr3_scan_map',
        args: { po3: frm.doc.purchase_order_v3 },
        callback: function (r) {
            var m = r.message || {};
            frm._scan = { po: frm.doc.purchase_order_v3, map: m.map || {}, names: m.names || {} };
        }
    });
}

function gr3_scan_feedback(frm, ok, msg) {
    var log = (frm.doc.scan_log || '').split('\n').filter(function (x) { return x; });
    log.unshift((ok ? '\u2713 ' : '\u2717 ') + msg);
    frm.set_value('scan_log', log.slice(0, 8).join('\n'));
    if (ok) { frappe.show_alert({ message: msg, indicator: 'green' }, 3); }
    else { frappe.show_alert({ message: msg, indicator: 'red' }, 5); beep_bad(); }
}

function beep_bad() {
    try {
        var c = new (window.AudioContext || window.webkitAudioContext)();
        var o = c.createOscillator(), g = c.createGain();
        o.connect(g); g.connect(c.destination);
        o.frequency.value = 220; o.type = 'square'; g.gain.value = 0.08;
        o.start(); setTimeout(function () { o.stop(); c.close(); }, 220);
    } catch (e) { /* no audio, the red alert is enough */ }
}

function gr3_apply_scan(frm, item_code, label, qty_override) {
    var step = flt(qty_override) || flt(frm.doc.scan_qty) || 1;
    var row = null;
    (frm.doc.items || []).forEach(function (d) {
        if (row) return;
        if (d.received_item_code !== item_code) return;
        // prefer a line that still has room, so repeat scans roll onto the
        // next line of the same item rather than over-filling the first
        if (flt(d.received_qty) < flt(d.expected_qty) || !flt(d.expected_qty)) row = d;
    });
    if (!row) {
        (frm.doc.items || []).forEach(function (d) {
            if (!row && d.received_item_code === item_code) row = d;
        });
    }
    var added = false;
    if (!row) {
        row = frm.add_child('items');
        row.received_item_code = item_code;
        row.received_qty = 0;
        row.accepted_qty = 0;
        row.rejected_qty = 0;
        row.disposition = 'Accept';
        added = true;
    }
    var was = flt(row.received_qty);
    frm._scan_undo = frm._scan_undo || [];
    frm._scan_undo.push({ row: row.name, was: was, added: added, label: label, step: step });
    row.received_qty = was + step;
    // rejects are decided by eye afterwards; a scan means "it physically arrived"
    row.accepted_qty = flt(row.received_qty) - flt(row.rejected_qty);
    frm.refresh_field('items');
    frm.dirty();

    var over = flt(row.expected_qty) && flt(row.received_qty) > flt(row.expected_qty);
    var txt = label + '  ' + flt(row.received_qty)
        + (flt(row.expected_qty) ? ' / ' + flt(row.expected_qty) : '');
    if (added) gr3_scan_feedback(frm, true, txt + '  (not on the order - added as a variance line)');
    else if (over) gr3_scan_feedback(frm, true, txt + '  \u2014 OVER');
    else gr3_scan_feedback(frm, true, txt);
}

function gr3_handle_scan(frm, code) {
    code = (code || '').trim();
    frm.set_value('scan_barcode', '');
    if (!code) return;
    // "ITEM x3" or "ITEM*3" counts three of it in one go
    var qty_override = null;
    var mult = code.match(/^(.*?)\s*[x*]\s*(\d+(?:\.\d+)?)$/i);
    if (mult) { code = mult[1].trim(); qty_override = flt(mult[2]); }
    if (!frm.doc.purchase_order_v3) {
        gr3_scan_feedback(frm, false, 'Pick a Purchase Order V3 first.');
        return;
    }
    var key = code.toUpperCase();
    var sc = frm._scan;
    if (sc && sc.map[key]) {
        var ic = sc.map[key];
        gr3_apply_scan(frm, ic, (sc.names[ic] || ic), qty_override);
        return;
    }
    // not on this order - could still be a real item (wrong item shipped)
    frappe.call({
        method: 'frappe.client.get_value',
        args: { doctype: 'Item', filters: { name: code }, fieldname: 'item_name' },
        callback: function (r) {
            if (r.message && r.message.item_name) {
                gr3_apply_scan(frm, code, r.message.item_name, qty_override);
            } else {
                gr3_scan_feedback(frm, false, code + ' \u2014 no matching item');
            }
        }
    });
}


function gr3_fetch_lines(frm) {
    // Ask the server what to expect - it is the only thing that knows which
    // shipment is arriving. Populate the grid WITHOUT saving: the warehouse
    // is not filled in yet, and saving here trips mandatory validation.
    // Counts always start at zero; the server re-derives everything on save.
    if (!frm.doc.purchase_order_v3) return;
    var filled = (frm.doc.items || []).filter(function (d) { return d.received_item_code; });
    if (filled.length) return;
    frappe.call({
        method: 'v3_gr3_prefill_preview',
        args: { po3: frm.doc.purchase_order_v3, shipment: frm.doc.inbound_shipment_v3 || '' },
        callback: function (r) {
            var m = (r.message || {});
            frm.clear_table('items');
            (m.rows || []).forEach(function (x) {
                var d = frm.add_child('items');
                d.po3_item = x.po3_item;
                d.expected_item_code = x.expected_item_code;
                d.received_item_code = x.received_item_code;
                d.retail_sku_suffix = x.retail_sku_suffix;
                d.expected_qty = x.expected_qty;
                d.received_qty = 0;
                d.accepted_qty = 0;
                d.rejected_qty = 0;
            });
            frm.refresh_field('items');
            if (m.shipment && !frm.doc.inbound_shipment_v3) frm.set_value('inbound_shipment_v3', m.shipment);
            if (m.warehouse && !frm.doc.warehouse) frm.set_value('warehouse', m.warehouse);
            frappe.show_alert({ message: __('Pulled ') + (m.rows || []).length
                + __(' open lines') + (m.shipment ? __(' from ') + m.shipment : ''),
                indicator: 'green' }, 5);
        }
    });
}

frappe.ui.form.on('Goods Receipt V3', {
    // deliberately NOT triggered on change - see gr3_bind_scan_enter
    scan_barcode: function (frm) { },
    onload_post_render: function (frm) { gr3_load_scan_map(frm); gr3_bind_scan_enter(frm); },
    purchase_order_v3: function (frm) {
        gr3_load_scan_map(frm);
        gr3_fetch_lines(frm);
    },
    refresh: function(frm) {
        gr3_bind_scan_enter(frm);
        frm.set_query('inbound_shipment_v3', function () {
            var f = { workflow_state: ['in', ['In Transit', 'Received']] };
            if (frm.doc.purchase_order_v3) f.purchase_order_v3 = frm.doc.purchase_order_v3;
            else if (frm.doc.supplier) f.supplier = frm.doc.supplier;
            return { filters: f };
        });
        if (frm.doc.docstatus === 0) {
            frm.add_custom_button(__('Undo Last Scan'), function () { gr3_undo_last_scan(frm); });
            frm.add_custom_button(__('Count All as Expected'), function () {
                frappe.confirm(__('Set every line to its expected quantity? Use this only when the delivery matched the paperwork.'),
                    function () { gr3_count_rows(frm, frm.doc.items || [], 'expected'); });
            }, __('Counting'));
            frm.add_custom_button(__('Count Selected as Expected'), function () {
                var r = gr3_selected_rows(frm);
                if (!r.length) { frappe.msgprint(__('Tick the lines you want first.')); return; }
                gr3_count_rows(frm, r, 'expected');
            }, __('Counting'));
            frm.add_custom_button(__('Reset Selected to Zero'), function () {
                var r = gr3_selected_rows(frm);
                gr3_count_rows(frm, r.length ? r : (frm.doc.items || []), 'zero');
            }, __('Counting'));
        }

        if (frm.doc.workflow_state === 'Ready to Post') {
            var acc = 0, rej = 0;
            (frm.doc.items || []).forEach(function (d) {
                acc += flt(d.accepted_qty);
                rej += flt(d.rejected_qty);
            });
            var bits = [(frm.doc.items || []).length + ' lines',
                acc + ' accepted \u2192 ' + (frm.doc.warehouse || '<i>no warehouse</i>')];
            if (rej) bits.push(rej + ' rejected \u2192 '
                + (frm.doc.rejected_warehouse || '<i>no rejected warehouse</i>'));
            if (frm.doc.variance_count) bits.push(frm.doc.variance_count + ' variance lines');
            frm.dashboard.set_headline(
                '<b>Post to Stock</b> will move stock and submit a Purchase Receipt against '
                + (frm.doc.purchase_order_v3 || 'the order')
                + '. This cannot be undone without cancelling that receipt.<br>'
                + bits.join(' &middot; '), 'orange');
        }

        if (frm.doc.docstatus === 1) {
            frm.add_custom_button(__('Supplier Claim'), function () {
                clm3_new_from('goods_receipt_v3', frm.doc.name);
            }, __('Create'));
        }

        if (frm.doc.docstatus === 0 && frm.doc.purchase_order_v3) {
            frm.add_custom_button(__('Fetch Open Lines'), function() {
                frm.clear_table('items');
                frm.refresh_field('items');
                gr3_fetch_lines(frm);
            });
        }
        if (frm.doc.purchase_order_v3) {
            frm.set_query('received_item_code', 'items', function() {
                return { filters: { name: ['in',
                    (frm._po3_items || []).length ? frm._po3_items : ['__none__']] } };
            });
            frappe.db.get_doc('Purchase Order V3', frm.doc.purchase_order_v3).then(function(po) {
                frm._po3_items = (po.items || []).map(function(r) { return r.item_code; });
            });
        }
        if (frm.doc.workflow_state === 'Posted') {
            frappe.db.get_value('Purchase Receipt', frm.doc.erp_purchase_receipt || '__none__', 'docstatus')
                .then(function(r) {
                    var ds = (r.message || {}).docstatus;
                    if (frm.doc.erp_purchase_receipt && ds === 1) {
                        frm.dashboard.set_headline(
                            __('Stock updated via Purchase Receipt {0}',
                               ['<a href="/app/purchase-receipt/' + frm.doc.erp_purchase_receipt + '">'
                                + frm.doc.erp_purchase_receipt + '</a>']));
                        return;
                    }
                    frm.dashboard.set_headline(
                        '<span style="color:var(--red-600)"><b>' +
                        __('Stock NOT updated — the Purchase Receipt is not submitted.') +
                        '</b></span>');
                    frm.add_custom_button(__('Retry ERP Posting'), function() {
                        frappe.call({
                            method: 'v3_retry_gr3_posting',
                            args: { gr3: frm.doc.name },
                            freeze: true,
                            freeze_message: __('Posting to ERP...'),
                            callback: function(res) {
                                var m = res.message || {};
                                frappe.msgprint(__('Purchase Receipt {0}: {1}', [m.pr, m.status]));
                                frm.reload_doc();
                            }
                        });
                    }).addClass('btn-primary');
                });
        }
    }
});
frappe.ui.form.on('Goods Receipt V3 Item', {
    received_qty: function(frm, cdt, cdn) {
        var row = locals[cdt][cdn];
        if (!flt(row.accepted_qty) && !flt(row.rejected_qty)) {
            frappe.model.set_value(cdt, cdn, 'accepted_qty', flt(row.received_qty));
        }
    }
});