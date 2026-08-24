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

frappe.ui.form.on('Purchase Order V3', {
    currency: po3_fx,
    supplier: function(frm) {
        if (!frm.doc.supplier) return;
        frappe.db.get_value('Supplier', frm.doc.supplier,
            ['default_price_list', 'default_currency', 'po3_order_email', 'po3_cc_email', 'po3_print_format'])
            .then(function(r) {
                var v = r.message || {};
                frm.set_value('buying_price_list', v.default_price_list || null);
                if (v.default_currency) frm.set_value('currency', v.default_currency);
                if (frm.is_new()) {
                    frm.set_value('supplier_email', v.po3_order_email || null);
                    frm.set_value('cc_email', v.po3_cc_email || null);
                    frm.set_value('po_print_format', v.po3_print_format || null);
                }
                if (!v.default_price_list) {
                    frappe.show_alert({ message: __('This supplier has no Default Price List - pick one manually.'), indicator: 'orange' });
                }
            });
    },
    buying_price_list: function(frm) {
        (frm.doc.items || []).forEach(function(d) {
            if (!d.rate) po3_pull_rate(frm, d.doctype, d.name);
        });
    },
    refresh: function(frm) {
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
                            method: 'v3_retry_po_submit', args: { po3: frm.doc.name },
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

frappe.ui.form.on('Purchase Order V3 Item', {
    item_code: po3_pull_rate,
    qty: po3_amount,
    rate: po3_amount
});