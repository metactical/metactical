frappe.ui.form.on("Item", {
    refresh: function (frm) {
        frm.trigger("load_website_specifications_options");
    },
    load_website_specifications_options: function (frm) {
        if (frm.doc.neb_website_specifications.length) {
            var labels = frm.doc.neb_website_specifications.map(
                (row) => row.label
            );

            frappe.call({
                method: "metactical.custom_scripts.item.item.get_website_specification_description_options",
                args: {
                    labels: labels,
                },
                callback: function (r) {
                    var descriptions = get_descriptions_dict(frm, r.message);
                    frm.events.update_web_specification_description_options(
                        frm,
                        descriptions
                    );
                },
            })
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
                    frm.clear_table("neb_website_specifications");
                    r.message.forEach((spec) => {
                        frm.add_child(
                            "neb_website_specifications",
                            {
                                label: spec.label,
                                mandatory: spec.mandatory,
                            }
                        );

                        if (!descriptions[spec.label]) {
                            descriptions[spec.label] = [];
                        }
                       
                        spec.descriptions.forEach((description) => {
                            descriptions[spec.label].push(description);
                        })
                    });
                    frm.refresh_field("neb_website_specifications");
                    frm.events.update_web_specification_description_options(
                        frm,
                        descriptions
                    );
                }
            },
        });
    },
    update_web_specification_description_options: function (frm, descriptions_obj) {
        if (!descriptions_obj) {
            return;
        }

        // Update the options of the description field
        const website_spec_label_rows = cur_frm.fields_dict["neb_website_specifications"].grid.grid_rows;
        var total_rows = website_spec_label_rows.length;
        var rows = website_spec_label_rows.map((row) => row.doc);
        var descriptions = [];

        // get the values for each object and add them to an array
        $.each(rows, function (index, row) {
            if (descriptions_obj[row.label]) {
                descriptions.push(descriptions_obj[row.label]);
            } else {
                descriptions.push([]);
            }
        });

        for (var row = 0; row < total_rows; row++) {
            if (rows[row].mandatory == 0) {
                descriptions[row].unshift("");
            }

            frappe.utils.filter_dict(
                website_spec_label_rows[row].docfields,
                { fieldname: "description" }
            )[0].options = descriptions[row];
        }

        frm.refresh_field("neb_website_specifications");
    },
});


function get_descriptions_dict(frm, r) {
    var descriptions = {};
    r.forEach((row) => {
        if (!descriptions[row.parent]) {
            descriptions[row.parent] = [];
        }

        descriptions[row.parent].push(row.description);
    });

    // get the values for each object and add them to an array
    frm.events.update_web_specification_description_options(
        frm,
        descriptions
    );
}