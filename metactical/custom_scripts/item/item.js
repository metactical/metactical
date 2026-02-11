frappe.ui.form.on("Item", {
    refresh: function (frm) {
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


