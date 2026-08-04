// Copyright (c) 2026, Storebuilder Commerce Inc and contributors
// For license information, please see license.txt

frappe.ui.form.on('ItemV2', {
    refresh(frm) {
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
                            if (frm.get_field('stock_levels_html'))
                                frm.get_field('stock_levels_html').html(html); 
                        } catch (e)
                        {}
                }
            });
        }
    }
});