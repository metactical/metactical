// Copyright (c) 2026, Storebuilder Commerce Inc and contributors
// For license information, please see license.txt

// Migrated from Client Script "Purchase Receipt V3 Form" (Form view).
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
    var soc = frm.doc.supplier_order_confirmation_v3 || '';
    if (frm._scan && frm._scan.po === frm.doc.purchase_order_v3 && frm._scan.soc === soc) return;
    frappe.call({
        method: 'metactical.metactical.doctype.purchase_receipt_v3.purchase_receipt_v3.v3_gr3_scan_map',
        args: { po3: frm.doc.purchase_order_v3, soc: soc },
        callback: function (r) {
            var m = r.message || {};
            frm._scan = { po: frm.doc.purchase_order_v3, soc: soc, map: m.map || {}, names: m.names || {} };
            // the order's items and the confirmation's (substitutes, new items)
            frm._po3_items = Object.keys(frm._scan.names);
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
        method: 'metactical.metactical.doctype.purchase_receipt_v3.purchase_receipt_v3.v3_gr3_prefill_preview',
        args: { po3: frm.doc.purchase_order_v3, shipment: frm.doc.inbound_shipment_v3 || '',
                soc: frm.doc.supplier_order_confirmation_v3 || '' },
        callback: function (r) {
            var m = (r.message || {});
            frm.clear_table('items');
            (m.rows || []).forEach(function (x) {
                var d = frm.add_child('items');
                d.soc3_item = x.soc3_item;
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

frappe.ui.form.on('Purchase Receipt V3', {
    // deliberately NOT triggered on change - see gr3_bind_scan_enter
    scan_barcode: function (frm) { },
    onload_post_render: function (frm) { gr3_load_scan_map(frm); gr3_bind_scan_enter(frm); },
    purchase_order_v3: function (frm) {
        gr3_load_scan_map(frm);
        gr3_fetch_lines(frm);
    },
    // a different confirmation expects different lines: re-pull them while
    // nothing has been counted yet
    supplier_order_confirmation_v3: function (frm) {
        gr3_load_scan_map(frm);
        var counted = (frm.doc.items || []).some(function (d) { return flt(d.received_qty); });
        if (frm.doc.docstatus === 0 && !counted) {
            frm.clear_table('items');
            frm.refresh_field('items');
            gr3_fetch_lines(frm);
        }
    },
    refresh: function(frm) {
        // Print the native twin with Purchase Receipt's own print formats, as
        // PO3 does with its native PO, so every PR format works here without a
        // PR3 copy. Unlike PO3 this holds in draft too: sync_native_pr rewrites
        // the twin on every save, so it always matches the last saved count.
        if (frm.doc.erp_purchase_receipt) {
            frm.print_doc = function() {
                if (frm.is_dirty()) {
                    frappe.toast({
                        message: __('Unsaved changes are not on the Purchase Receipt yet - save first to print them.'),
                        indicator: 'yellow'
                    });
                }
                frappe.set_route('print', 'Purchase Receipt', frm.doc.erp_purchase_receipt);
            };
        } else {
            delete frm.print_doc;
        }
        gr3_bind_scan_enter(frm);
        // a draft whose native twin refused the last save - say so where it
        // cannot be missed, until a save brings the two back in step
        if (frm.doc.docstatus === 0 && frm.doc.post_error) {
            frm.dashboard.set_headline('<span style="color:var(--red-600)"><b>'
                + __('Draft Purchase Receipt {0} is out of date.', [frm.doc.erp_purchase_receipt || ''])
                + '</b> ' + frappe.utils.escape_html(frm.doc.post_error) + '</span>');
        }
        frm.set_query('supplier_order_confirmation_v3', function () {
            var f = { docstatus: 1 };
            if (frm.doc.purchase_order_v3) f.purchase_order_v3 = frm.doc.purchase_order_v3;
            return { filters: f };
        });
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

        // the draft native twin, kept in step with the count (see sync_native_pr)
        if (frm.doc.docstatus === 0 && frm.doc.erp_purchase_receipt) {
            frm.add_custom_button(__('Draft Purchase Receipt'), function () {
                frappe.set_route('Form', 'Purchase Receipt', frm.doc.erp_purchase_receipt);
            }, __('View'));
        }

        if (frm.doc.docstatus === 1) {
            frm.add_custom_button(__('Supplier Claim'), function () {
                clm3_new_from('purchase_receipt_v3', frm.doc.name);
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
                            method: 'metactical.metactical.doctype.purchase_receipt_v3.purchase_receipt_v3.v3_retry_gr3_posting',
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
// A new Received count starts the row over as all accepted, nothing rejected -
// otherwise Accepted keeps the old figure and Finish Counting refuses it. What
// the user then types into Accepted / Rejected is left as they set it.
frappe.ui.form.on('Purchase Receipt V3 Item', {
    received_qty: function(frm, cdt, cdn) {
        var row = locals[cdt][cdn];
        frappe.model.set_value(cdt, cdn, {
            accepted_qty: flt(row.received_qty),
            rejected_qty: 0
        });
    }
});

// ---------------------------------------------------------------------------
// Migrated from Client Script "Purchase Receipt V3 Stale State Guard" (Form view).
// Refuses a workflow action when the document has already moved on in the DB,
// so the user re-picks from the refreshed action list. This flow has the most
// states to slip between (Counting / Variance Review / Ready to Post / Posted).
// ---------------------------------------------------------------------------

frappe.ui.form.on('Purchase Receipt V3', {
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

// ---------------------------------------------------------------------------
// Taxes and Charges -- the native Purchase Receipt's own fields and child
// table, as on PO3 and SOC3. A new receipt starts with the live confirmation's
// taxes and discount (copied on its first save); totals are worked out by
// ERPNext's own engine (metactical/procurement_v3/taxes.py) on save, and while
// the form is being edited through preview_totals.
// ---------------------------------------------------------------------------

// The native form's tax-grid behaviour: Rate editable and required, Amount
// read-only -- the other way round for "Actual" -- the account query and the
// row checks.
erpnext.accounts.taxes.setup_tax_validations('Purchase Receipt V3');

var GR3_TOTAL_FIELDS = ['total', 'total_qty', 'base_total', 'net_total', 'base_net_total',
    'taxes_and_charges_added', 'base_taxes_and_charges_added',
    'taxes_and_charges_deducted', 'base_taxes_and_charges_deducted',
    'total_taxes_and_charges', 'base_total_taxes_and_charges',
    'discount_amount', 'base_discount_amount', 'grand_total', 'base_grand_total',
    'rounding_adjustment', 'base_rounding_adjustment', 'rounded_total', 'base_rounded_total'];

// Debounced: a burst of edits (a template's rows, a run of scans) makes one
// call, and an answer to an older call is dropped. Nothing to work out on a
// receipt that has never been saved: its lines have no rate until then.
function gr3_calc_taxes(frm) {
    if (frm.doc.docstatus !== 0 || frm.is_new()) return;
    clearTimeout(frm._gr3_calc_timer);
    frm._gr3_calc_timer = setTimeout(function() {
        var seq = frm._gr3_calc_seq = (frm._gr3_calc_seq || 0) + 1;
        frappe.call({
            method: 'metactical.metactical.doctype.purchase_receipt_v3.purchase_receipt_v3.preview_totals',
            args: { doc: frm.doc },
            callback: function(r) {
                if (seq !== frm._gr3_calc_seq || !r.message) return;
                // assigned rather than set_value: display copies of what save
                // recomputes, and set_value would fire these handlers again
                GR3_TOTAL_FIELDS.forEach(function(f) {
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
                    d.amount = calc.amount;
                    d.net_rate = calc.net_rate;
                    d.net_amount = calc.net_amount;
                });
                GR3_TOTAL_FIELDS.forEach(function(f) { frm.refresh_field(f); });
                frm.refresh_field('taxes');
            }
        });
    }, 300);
}

frappe.ui.form.on('Purchase Receipt V3', {
    setup: function(frm) {
        frm.set_query('taxes_and_charges', function() {
            return { filters: { company: frm.doc.company, disabled: 0 } };
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
                gr3_calc_taxes(frm);
            }
        });
    },
    apply_discount_on: function(frm) { gr3_calc_taxes(frm); },
    additional_discount_percentage: function(frm) { gr3_calc_taxes(frm); },
    discount_amount: function(frm) { gr3_calc_taxes(frm); },
    disable_rounded_total: function(frm) { gr3_calc_taxes(frm); },
    taxes_remove: function(frm) { gr3_calc_taxes(frm); },
    // Description is mandatory on ERPNext's tax row, but picking the account
    // is all that is needed: fill it from the account, as the native form
    // does -- save fills it too (prepare_tax_rows).
    validate: function(frm) { gr3_tax_descriptions(frm); }
});

function gr3_tax_descriptions(frm) {
    (frm.doc.taxes || []).forEach(function(t) {
        if (t.account_head && !t.description) {
            t.description = t.account_head.split(' - ').slice(0, -1).join(' - ') || t.account_head;
        }
        // this row's own copy of the field, so the native forms are unaffected
        var df = frappe.meta.get_docfield(t.doctype, 'description', t.name);
        if (df) df.reqd = 0;
    });
    frm.refresh_field('taxes');
}

// What is counted is what is priced, so a change to the count moves the taxes.
frappe.ui.form.on('Purchase Receipt V3 Item', {
    accepted_qty: function(frm) { gr3_calc_taxes(frm); },
    rejected_qty: function(frm) { gr3_calc_taxes(frm); },
    received_qty: function(frm) { gr3_calc_taxes(frm); },
    items_remove: function(frm) { gr3_calc_taxes(frm); }
});

// The tax row itself. Purchase Taxes and Charges is shared with the native
// forms, PO3 and SOC3, so these only act on a receipt. Picking an account
// fills Rate and Description as the native form does (erpnext accounts.js).
frappe.ui.form.on('Purchase Taxes and Charges', {
    account_head: function(frm, cdt, cdn) {
        if (frm.doctype !== 'Purchase Receipt V3') return;
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
                    gr3_calc_taxes(frm);
                }
            });
        }
    },
    charge_type: function(frm, cdt, cdn) {
        if (frm.doctype !== 'Purchase Receipt V3') return;
        erpnext.accounts.taxes.validate_taxes_and_charges(cdt, cdn);
        var row = frm.open_grid_row() || frm.get_field('taxes').grid.get_row(cdn);
        erpnext.accounts.taxes.set_conditional_mandatory_rate_or_amount(row);
        gr3_calc_taxes(frm);
    },
    rate: function(frm, cdt, cdn) {
        if (frm.doctype !== 'Purchase Receipt V3') return;
        erpnext.accounts.taxes.validate_taxes_and_charges(cdt, cdn);
        gr3_calc_taxes(frm);
    },
    tax_amount: function(frm, cdt, cdn) {
        if (frm.doctype !== 'Purchase Receipt V3') return;
        erpnext.accounts.taxes.validate_taxes_and_charges(cdt, cdn);
        gr3_calc_taxes(frm);
    },
    row_id: function(frm, cdt, cdn) {
        if (frm.doctype !== 'Purchase Receipt V3') return;
        erpnext.accounts.taxes.validate_taxes_and_charges(cdt, cdn);
        gr3_calc_taxes(frm);
    },
    add_deduct_tax: function(frm) {
        if (frm.doctype === 'Purchase Receipt V3') gr3_calc_taxes(frm);
    },
    category: function(frm) {
        if (frm.doctype === 'Purchase Receipt V3') gr3_calc_taxes(frm);
    },
    included_in_print_rate: function(frm) {
        if (frm.doctype === 'Purchase Receipt V3') gr3_calc_taxes(frm);
    }
});
