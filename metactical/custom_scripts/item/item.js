frappe.ui.form.on("Item", {
    refresh: function (frm) {
        frm.trigger("add_item_details_action_buttons");
        metactical.utils.load_website_specifications_options(frm);
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
    label: function(frm, cdt, cdn) {
        metactical.utils.load_website_specifications_options(frm);
    },
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


