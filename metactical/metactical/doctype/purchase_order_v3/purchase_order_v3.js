// Copyright (c) 2026, Storebuilder Commerce Inc and contributors
// For license information, please see license.txt

// Migrated from Client Script "Purchase Order V3 Form" (Form view).

function po3_new_linked(doctype, po_name) {
    frappe.model.with_doctype(doctype, function() {
        var doc = frappe.model.get_new_doc(doctype);
        doc.purchase_order_v3 = po_name;
        frappe.set_route('Form', doctype, doc.name);
    });
}


function po3_pull_rate(frm, cdt, cdn) {
    var row = locals[cdt][cdn];
    if (!row.item_code || !frm.doc.buying_price_list) return;
    frappe.db.get_value('Item Price',
        { item_code: row.item_code, price_list: frm.doc.buying_price_list, buying: 1 },
        'price_list_rate').then(function(r) {
            if (r.message && r.message.price_list_rate && !row.rate) {
                frappe.model.set_value(cdt, cdn, 'rate', r.message.price_list_rate);
            }
        });
}
function po3_amount(frm, cdt, cdn) {
    var row = locals[cdt][cdn];
    frappe.model.set_value(cdt, cdn, 'amount', flt(row.qty) * flt(row.rate));
}

function po3_fx(frm) {
    if (!frm.doc.currency || !frm.doc.company) return;
    frappe.db.get_value('Company', frm.doc.company, 'default_currency').then(function(r) {
        var cc = (r.message || {}).default_currency;
        if (!cc || frm.doc.currency === cc) { frm.set_value('conversion_rate', 1); return; }
        frappe.call({
            method: 'erpnext.setup.utils.get_exchange_rate',
            args: { from_currency: frm.doc.currency, to_currency: cc },
            callback: function(res) {
                if (res.message) frm.set_value('conversion_rate', res.message);
            }
        });
    });
}

function po3_split(line, sep) {
    if (sep === '\t') return line.split('\t');
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

// Header names are matched loosely - lower-cased with punctuation stripped - so
// "DSupplier Cost ($)", "dsupplier cost" and "supplier_cost" all land on rate.
function po3_norm_header(h) {
    return String(h == null ? '' : h).toLowerCase().replace(/[^a-z0-9]/g, '');
}

var PO3_PASTE_COLS = {
    code: ['erpitemcode', 'itemcode', 'item', 'itemid', 'sku', 'retailsku'],
    qty:  ['qtytoordered', 'qty', 'quantity', 'orderqty', 'suggestedorderqtyv2', 'suggestedorderqty'],
    rate: ['dsuppliercost', 'suppliercost', 'unitcost', 'rate', 'cost', 'price']
};

// How far down the paste to hunt for the header row.
var PO3_HEADER_SCAN = 30;

function po3_find_cols(hdr) {
    var idx = {};
    Object.keys(PO3_PASTE_COLS).forEach(function(key) {
        idx[key] = -1;
        PO3_PASTE_COLS[key].some(function(want) {
            var at = hdr.indexOf(want);
            if (at !== -1) { idx[key] = at; return true; }
            return false;
        });
    });
    return idx;
}

function po3_paste_items(frm) {
    if (frm.doc.docstatus !== 0) {
        frappe.msgprint(__('Items can only be pasted while the order is a draft.'));
        return;
    }
    var d = new frappe.ui.Dialog({
        title: __('Paste items from Excel'),
        size: 'large',
        fields: [
            { fieldtype: 'HTML', options:
                '<p style="margin-bottom:8px"><b>Select the whole sheet and paste it here.</b> '
                + 'Title and grouping rows above the header are ignored, and so is every '
                + 'column except <code>Erp Item Code</code>, <code>QtyToOrdered</code> and '
                + '<code>DSupplier Cost ($)</code>.<br>Only rows with a QtyToOrdered above 0 '
                + 'are brought in. Items are matched on item code, retail SKU, barcode or '
                + 'supplier part number.</p>' },
            { fieldtype: 'Check', fieldname: 'replace', label: __('Replace the existing lines'),
              default: 0, description: __('Off: pasted rows are added to what is already there.') },
            { fieldtype: 'Small Text', fieldname: 'data', label: __('Pasted rows'), reqd: 1 }
        ],
        primary_action_label: __('Add items'),
        primary_action: function(v) {
            var lines = (v.data || '').split(/\r?\n/).filter(function(l) { return l.trim(); });
            if (!lines.length) return;
            var sep = (v.data || '').indexOf('\t') !== -1 ? '\t' : ',';
            var clean = function(x) { return String(x == null ? '' : x).trim().replace(/^"|"$/g, ''); };

            // The report is copied whole, so a banner line and a row of group bands
            // ("SKU / BARCODE INFO", "ORDER INFO", ...) sit above the real header.
            // Find the first row that names both a code column and a quantity column
            // and treat everything above it as noise.
            var idx = null, hdr_row = -1;
            for (var i = 0; i < Math.min(lines.length, PO3_HEADER_SCAN); i++) {
                var cand = po3_find_cols(po3_split(lines[i], sep).map(po3_norm_header));
                if (cand.code !== -1 && cand.qty !== -1) { idx = cand; hdr_row = i; break; }
            }
            if (!idx) {
                frappe.msgprint(__('No header row was found in the first {0} rows. The paste needs a row naming an item code column and a quantity column, for example Erp Item Code and QtyToOrdered.', [PO3_HEADER_SCAN]));
                return;
            }

            var rows = [];
            lines.slice(hdr_row + 1).forEach(function(l) {
                var cells = po3_split(l, sep).map(clean);
                var code = cells[idx.code];
                if (!code) return;
                rows.push({
                    code: code,
                    qty: cells[idx.qty],
                    rate: idx.rate !== -1 ? cells[idx.rate] : 0
                });
            });
            if (!rows.length) {
                frappe.msgprint(__('Nothing to add - no data rows under the header.'));
                return;
            }

            frappe.call({
                method: 'metactical.metactical.doctype.purchase_order_v3.purchase_order_v3.resolve_pasted_items',
                args: { rows: rows, supplier: frm.doc.supplier, price_list: frm.doc.buying_price_list },
                freeze: true,
                freeze_message: __('Matching {0} row(s)...', [rows.length]),
                callback: function(r) {
                    if (r.exc) return;
                    var res = r.message || {};
                    var items = res.items || [];
                    if (v.replace) frm.clear_table('items');
                    else if ((frm.doc.items || []).length === 1 && !frm.doc.items[0].item_code) {
                        frm.clear_table('items');
                    }
                    items.forEach(function(it) {
                        var row = frm.add_child('items');
                        row.item_code = it.item_code;
                        row.item_name = it.item_name;
                        row.uom = it.uom;
                        row.retail_sku_suffix = it.retail_sku_suffix;
                        if (it.supplier_part_no) row.supplier_part_no = it.supplier_part_no;
                        if (it.barcode) row.barcode = it.barcode;
                        row.qty = it.qty;
                        if (it.rate) row.rate = it.rate;
                        row.amount = flt(it.qty) * flt(it.rate);
                    });
                    d.hide();
                    frm.refresh_field('items');

                    var msg = __('Added {0} item(s).', [items.length]);
                    if (res.skipped_zero_qty) {
                        msg += '<br>' + __('{0} row(s) skipped for a quantity of 0.', [res.skipped_zero_qty]);
                    }
                    if ((res.unknown || []).length) {
                        msg += '<br><br><b>' + __('Not matched to an item ({0}):', [res.unknown.length])
                             + '</b> ' + res.unknown.slice(0, 25).join(', ')
                             + (res.unknown.length > 25 ? ' &hellip;' : '');
                    }
                    msg += '<br><br>' + __('Review the lines, then Save.');
                    frappe.msgprint({
                        title: __('Paste applied'), message: msg,
                        indicator: items.length ? 'green' : 'orange'
                    });
                }
            });
        }
    });
    d.show();
}

// Amend hands back a copy of the cancelled order that deliberately keeps the
// no_copy fields (create_new.js: `!from_amend && df.no_copy`), so the draft
// opens showing that order's workflow state, its native PO and every line's
// confirmed / received progress. The server clears all of it on insert; clear
// it here as well so the buyer works on an order that already reads like a new
// one, instead of one still claiming lines were confirmed against a PO that no
// longer exists.
//
// Driven off the same no_copy flags the server uses, so the two cannot drift.
var PO3_AMEND_KEEP = ['amended_from', 'material_request', 'material_request_item'];
var PO3_NUMERIC = ['Int', 'Float', 'Currency', 'Percent', 'Check'];

function po3_reset_amended(frm) {
    if (!frm.is_new() || !frm.doc.amended_from) return;

    var blank = function(doc) {
        var fields = frappe.meta.docfield_list[doc.doctype]
            || (frappe.get_meta(doc.doctype) || {}).fields || [];
        fields.forEach(function(df) {
            if (!cint(df.no_copy) || PO3_AMEND_KEEP.indexOf(df.fieldname) !== -1) return;
            doc[df.fieldname] = PO3_NUMERIC.indexOf(df.fieldtype) !== -1
                ? (flt(df.default) || 0)
                : (df.default || null);
        });
    };

    blank(frm.doc);
    (frm.doc.items || []).forEach(blank);
    frm.doc.workflow_state = null;
}


// Shows the picked address straight away; the server re-renders it on save.
function po3_render_address(frm, field, display_field) {
    if (!frm.doc[field]) {
        frm.set_value(display_field, null);
        return;
    }
    frappe.call({
        method: 'frappe.contacts.doctype.address.address.get_address_display',
        args: { address_dict: frm.doc[field] },
        callback: function(r) { frm.set_value(display_field, r.message || null); }
    });
}

frappe.ui.form.on('Purchase Order V3', {
    onload: po3_reset_amended,

    // Mirrors metactical's own override of this button on native Purchase
    // Order, not stock ERPNext's. get_all_items makes the server pull every
    // open Material Request for the supplier at once, so there is no document
    // picker - the items just land in the grid.
    get_items_from_open_material_requests: function(frm) {
        if (!frm.doc.supplier) {
            frappe.msgprint(__('Pick a Supplier first.'));
            return;
        }
        // drop the blank starter row so the fetched lines are not appended after it
        if ((frm.doc.items || []).length === 1 && !frm.doc.items[0].item_code) {
            frm.clear_table('items');
        }
        frappe.call({
            type: 'POST',
            method: 'frappe.model.mapper.map_docs',
            args: {
                method: 'metactical.metactical.doctype.purchase_order_v3.purchase_order_v3.make_po3_based_on_supplier',
                source_names: [frm.doc.supplier],
                target_doc: frm.doc,
                // blank Ship To Warehouse = requests for every warehouse
                args: { supplier: frm.doc.supplier, get_all_items: true, warehouse: frm.doc.set_warehouse || null }
            },
            freeze: true,
            freeze_message: __('Fetching items from open Material Requests...'),
            callback: function(r) {
                if (r.exc) return;
                frappe.model.sync(r.message);
                frm.dirty();
                frm.refresh();
                var n = (frm.doc.items || []).filter(function(d) { return d.item_code; }).length;
                frappe.show_alert({
                    message: n
                        ? __('{0} item(s) fetched from open Material Requests.', [n])
                        : (frm.doc.set_warehouse
                            ? __('No open Material Requests found for this supplier and {0}.', [frm.doc.set_warehouse])
                            : __('No open Material Requests found for this supplier.')),
                    indicator: n ? 'green' : 'orange'
                });
            }
        });
    },

    currency: po3_fx,

    // A new destination has to take the lines with it.
    set_warehouse: function(frm) {
        if (frm.doc.docstatus !== 0) return;

        // Take the lines with it. A line left on the old warehouse is stock
        // received somewhere nobody chose, and ERPNext blanks the native PO's
        // Set Target Warehouse outright when its lines disagree. Same thing
        // ERPNext does on this field (autofill_warehouse).
        (frm.doc.items || []).forEach(function(row) {
            if (row.warehouse !== frm.doc.set_warehouse) {
                frappe.model.set_value(row.doctype, row.name, 'warehouse', frm.doc.set_warehouse);
            }
        });
    },
    supplier: function(frm) {
        if (!frm.doc.supplier) return;
        frappe.db.get_value('Supplier', frm.doc.supplier,
            ['default_price_list', 'default_currency', 'po3_order_email', 'po3_cc_email', 'po3_print_format',
             'nat_sender_email_account', 'nat_shipping_address', 'nat_billing_address'])
            .then(function(r) {
                var v = r.message || {};
                frm.set_value('buying_price_list', v.default_price_list || null);
                if (v.default_currency) frm.set_value('currency', v.default_currency);
                // a different supplier ships and bills under its own addresses
                frm.set_value('shipping_address', v.nat_shipping_address || null);
                frm.set_value('billing_address', v.nat_billing_address || null);
                if (frm.is_new()) {
                    frm.set_value('supplier_email', v.po3_order_email || null);
                    frm.set_value('cc_email', v.po3_cc_email || null);
                    frm.set_value('po_print_format', v.po3_print_format || null);
                    // sender_email follows via fetch_from on sender_email_account
                    frm.set_value('sender_email_account', v.nat_sender_email_account || null);
                }
                if (!v.default_price_list) {
                    frappe.show_alert({ message: __('This supplier has no Default Price List - pick one manually.'), indicator: 'orange' });
                }
            });
    },
    shipping_address: function(frm) {
        po3_render_address(frm, 'shipping_address', 'shipping_address_display');
    },
    billing_address: function(frm) {
        po3_render_address(frm, 'billing_address', 'billing_address_display');
    },
    buying_price_list: function(frm) {
        (frm.doc.items || []).forEach(function(d) {
            if (!d.rate) po3_pull_rate(frm, d.doctype, d.name);
        });
    },
    refresh: function(frm) {
        if (frm.doc.docstatus === 0) {
            frm.add_custom_button(__('⭱ Paste Items'), function() { po3_paste_items(frm); });
        }
        if (frm.doc.docstatus !== 1) return;
        var st = frm.doc.workflow_state;
        var closed = ['Closed', 'Closed Short', 'Cancelled'].indexOf(st) !== -1;

        // One confirmation per PO, so its Connections tile is hidden. Look it
        // up and surface it as a headline + a button that adapts to state.
        frappe.call({
            method: 'frappe.client.get_list',
            args: {
                doctype: 'Supplier Order Confirmation V3',
                filters: { purchase_order_v3: frm.doc.name, docstatus: ['<', 2] },
                fields: ['name', 'workflow_state'], limit_page_length: 1
            },
            callback: function(r) {
                var soc = (r.message || [])[0];
                var bits = [];
                if (frm.doc.erp_purchase_order) {
                    bits.push(__('Native PO') + ': <a href="/app/purchase-order/'
                        + frm.doc.erp_purchase_order + '">' + frm.doc.erp_purchase_order + '</a>');
                }
                if (soc) {
                    bits.push(__('Confirmation') + ': <a href="/app/supplier-order-confirmation-v3/'
                        + soc.name + '">' + soc.name + '</a> <span class="text-muted">('
                        + __(soc.workflow_state || '') + ')</span>');
                } else if (!closed) {
                    bits.push('<span class="text-muted">' + __('No supplier confirmation yet') + '</span>');
                }
                if (bits.length) frm.dashboard.set_headline(bits.join(' &nbsp;·&nbsp; '));

                if (closed) return;
                if (soc) {
                    frm.add_custom_button(__('Supplier Confirmation {0}', [soc.name]), function() {
                        frappe.set_route('Form', 'Supplier Order Confirmation V3', soc.name);
                    });
                } else {
                    frm.add_custom_button(__('Create Supplier Confirmation'), function() {
                        po3_new_linked('Supplier Order Confirmation V3', frm.doc.name);
                    });
                }
            }
        });

        // a twin that never submitted must not look successful
        if (frm.doc.erp_purchase_order) {
            frappe.db.get_value('Purchase Order', frm.doc.erp_purchase_order, 'docstatus')
                .then(function(r) {
                    var ds = (r.message || {}).docstatus;
                    if (ds !== 0) return;
                    frm.dashboard.set_headline(
                        '<span style="color:var(--red-600)"><b>' +
                        __('Native PO {0} is still a DRAFT — it was not submitted.', [frm.doc.erp_purchase_order]) +
                        '</b></span>' + (frm.doc.post_error ? '<br>' + frappe.utils.escape_html(frm.doc.post_error) : ''));
                    frm.add_custom_button(__('Retry Native PO'), function() {
                        frappe.call({
                            method: 'metactical.metactical.doctype.purchase_order_v3.purchase_order_v3.v3_retry_po_submit',
                            args: { po3: frm.doc.name },
                            freeze: true, freeze_message: __('Submitting native PO…'),
                            callback: function(res) {
                                var m = res.message || {};
                                frappe.msgprint(__('Native PO {0}: {1}', [m.po, m.status]));
                                frm.reload_doc();
                            }
                        });
                    }).addClass('btn-danger');
                });
        }

        if (closed) return;
        var mk = function(label, doctype) {
            frm.add_custom_button(__(label), function() {
                po3_new_linked(doctype, frm.doc.name);
            }, __('Create'));
        };
        mk('Inbound Shipment', 'Inbound Shipment V3');
        mk('Goods Receipt', 'Goods Receipt V3');
        mk('Supplier Claim', 'Supplier Claim V3');
        if (frm.doc.erp_purchase_order) {
            frm.add_custom_button(__('Native PO'), function() {
                frappe.set_route('Form', 'Purchase Order', frm.doc.erp_purchase_order);
            }, __('View'));
        }
    }
});

// A new item on the line means a new barcode and supplier SKU -- replace, not
// keep, whatever the previous item left there.
function po3_pull_identifiers(frm, cdt, cdn) {
    var row = locals[cdt][cdn];
    if (!row.item_code) return;
    frappe.call({
        method: 'metactical.metactical.doctype.purchase_order_v3.purchase_order_v3.get_item_identifiers',
        args: { item_code: row.item_code, supplier: frm.doc.supplier },
        callback: function(r) {
            var v = r.message || {};
            frappe.model.set_value(cdt, cdn, 'barcode', v.barcode || null);
            frappe.model.set_value(cdt, cdn, 'supplier_part_no', v.supplier_part_no || null);
        }
    });
}

frappe.ui.form.on('Purchase Order V3 Item', {
    item_code: function(frm, cdt, cdn) {
        po3_pull_rate(frm, cdt, cdn);
        po3_pull_identifiers(frm, cdt, cdn);
    },
    qty: po3_amount,
    rate: po3_amount
});

// ---------------------------------------------------------------------------
// Migrated from Client Script "Purchase Order V3 Stale State Guard" (Form view).
// Refuses a workflow action when the document has already moved on in the DB,
// so the user re-picks from the refreshed action list instead of acting on a
// stale state.
// ---------------------------------------------------------------------------

frappe.ui.form.on('Purchase Order V3', {
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