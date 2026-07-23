frappe.ui.form.on("Item", {
    refresh: function (frm) {
        frm.trigger("add_item_details_action_buttons");
        metactical.utils.load_website_specifications_options(frm);

        // Disabled = grey (native style); else color by type. Status kept in text.
        const color = frm.doc.disabled ? 'grey' : (frm.doc.has_variants ? 'orange' : (frm.doc.variant_of ? 'blue' : 'grey'));
        const statusText = frm.doc.disabled ? 'Disabled' : 'Enabled';
        const type = frm.doc.has_variants ? 'Template' : (frm.doc.variant_of ? 'Variant' : 'Simple Item');
        frm.page.set_indicator(statusText + ' · ' + type, color);

        const applyConn = () => {
            const isTemplate = !!frm.doc.has_variants;
            try {
                    if (frm.dashboard && frm.dashboard.links_area)
                        frm.dashboard.links_area.toggle(!isTemplate); 
                } catch (e)
                {}
            frm.$wrapper.find('.form-dashboard-section').each(function () {
                const t = ($(this).find('.section-head, .h6, .form-section-heading').first().text() || '').trim();
                if (t.toLowerCase() === 'connections') 
                    $(this).toggle(!isTemplate);
            });
        };
        
        applyConn(); 
        setTimeout(applyConn, 400);
        setTimeout(applyConn, 1200);

        if (!frm.is_new()) {
            frappe.call({
                method: 'frappe.client.get_list',
                args: {
                    doctype: 'Bin',
                    filters:
                    { 
                        item_code: frm.doc.name,
                        actual_qty: ['>', 0] 
                    },
                    fields: ['warehouse','actual_qty','reserved_qty','projected_qty'], 
                    order_by: 'actual_qty desc',
                    limit_page_length: 50 
                },
                callback(r) {
                    const rows = r.message || [];
                    let html;
                    if (!rows.length) {
                        html = '<div class="text-muted" style="padding:6px 2px;">No Stock Available Currently</div>'; 
                    }
                    else {
                        const totActual = rows.reduce((a,x)=>a+(x.actual_qty||0),0);
                        const totReserved = rows.reduce((a,x)=>a+(x.reserved_qty||0),0);
                        const totProjected = rows.reduce((a,x)=>a+(x.projected_qty||0),0);
                        html = '<table class="table table-bordered" style="margin:0;font-size:12px;">'+
                                    '<thead>'+
                                        '<tr>'+
                                            '<th>Warehouse</th>'+
                                            '<th style="text-align:right">Actual</th>'+
                                            '<th style="text-align:right">Reserved</th>'+
                                            '<th style="text-align:right">Projected</th>'+
                                        '</tr>'+
                                    '</thead>'+
                                '<tbody>'+
                            rows.map(x=>
                                `<tr>
                                    <td>${frappe.utils.escape_html(x.warehouse||'')}</td>
                                    <td style="text-align:right">${x.actual_qty||0}</td>
                                    <td style="text-align:right">${x.reserved_qty||0}</td>
                                    <td style="text-align:right">${x.projected_qty||0}</td>
                                </tr>`).join('') +
                                `<tr style="font-weight:600;">
                                    <td>Total</td>
                                    <td style="text-align:right">${totActual}</td>
                                    <td style="text-align:right">${totReserved}</td>
                                    <td style="text-align:right">${totProjected}</td>
                                </tr>
                            </tbody>
                        </table>`;
                    }
                    try {
                            if (frm.get_field('nat_stock_levels_html'))
                                frm.get_field('nat_stock_levels_html').html(html); 
                        } catch (e)
                        {}
                }
            });
        }
    },
    neb_copy_from_item_group: function (frm) {
        if (!frm.doc.item_group) {
            frappe.msgprint(__("Please set Item Group first"));
            return;
        }

        return frm.call({
            method: "metactical.custom_scripts.item.item.copy_specification_from_item_group",
            args: { item_group: frm.doc.item_group },
            callback: function (r) {
                if (r.message.length) {
                    var descriptions = {};
                
                    // Collect incoming labels
                    let incoming_labels = r.message.map(spec => spec.label);
                
                    // Collect existing labels from the form
                    let existing_labels = (frm.doc.neb_website_specifications || []).map(
                        row => row.label
                    );
                
                    // ---- Remove deleted rows ----
                    frm.doc.neb_website_specifications = 
                        (frm.doc.neb_website_specifications || []).filter(row => {
                            return incoming_labels.includes(row.label);
                        });
                
                    // ---- Add new rows ----
                    r.message.forEach((spec) => {
                        if (!existing_labels.includes(spec.label)) {
                            frm.add_child("neb_website_specifications", {
                                label: spec.label,
                                mandatory: spec.mandatory,
                            });
                        }
                
                        // Update descriptions map
                        if (!descriptions[spec.label]) {
                            descriptions[spec.label] = [];
                        }
                        (spec.descriptions || []).forEach((description) => {
                            descriptions[spec.label].push(description);
                        });
                    });
                
                    // Refresh field + update descriptions
                    frm.refresh_field("neb_website_specifications");
                    metactical.utils.update_web_specification_description_options(
                        frm,
                        descriptions
                    );
                }
            },
        });
    },
    add_item_details_action_buttons: function(frm) {
        const grid = frm.fields_dict["item_detail"].grid;
        if (!grid) return;

        // Avoid adding buttons multiple times
        if (grid.custom_buttons_added) return;
        grid.custom_buttons_added = true;

        grid.add_custom_button(__('Load Data From SB'), function() {
            frappe.call({
                freeze: true,
                method: "metactical.custom_scripts.item.item.get_item_details",
                args: {
                    item_code: frm.doc.item_code
                },
                callback: function(r) {
                    if (r.message) {
                        frm.reload_doc();
                        
                        let messages = r.message
                        messages.forEach(msg => {
                            frappe.msgprint({
                                title: __('Item Detail Load Status'),
                                message: msg.message,
                                indicator: msg.success ? 'green' : 'red'
                            });
                        })
                    }
                },
            });
        });
    },
});

frappe.ui.form.on("MT Item Website Specification", {
    description: function (frm, cdt, cdn) {
        var row = locals[cdt][cdn];
        frappe.call({
            method: "metactical.custom_scripts.item.item.get_sb_tag",
            args: {
                description: row.description,
                label: row.label,
            },
            callback: function (r) {
                if (r.message) {
                    
                }
            },
        });
    },
});

frappe.ui.form.on("Item SB Tag", {
    sb_tag: function (frm, cdt, cdn) {
        var row = locals[cdt][cdn];
        row.manual_selection = 1;
    },
});


