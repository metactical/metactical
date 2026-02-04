frappe.provide("metactical.utils");

metactical.utils.format_currency = function(value) {
    return format_currency(value, frappe.defaults.get_default("currency"));
};

metactical.utils.show_alert = function(message) {
    frappe.show_alert({
        message: message,
        indicator: "green"
    });
};

metactical.utils.load_website_specifications_options = function (frm) {
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
                var descriptions = metactical.utils.get_descriptions_dict(frm, r.message);
                metactical.utils.update_web_specification_description_options(
                    frm,
                    descriptions
                );
            },
        })
    }
}

metactical.utils.update_web_specification_description_options = function (frm, descriptions_obj) {
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
};

metactical.utils.get_descriptions_dict = function(frm, r) {
    var descriptions = {};
    r.forEach((row) => {
        if (!descriptions[row.parent]) {
            descriptions[row.parent] = [];
        }

        descriptions[row.parent].push(row.description);
    });

    // get the values for each object and add them to an array
    metactical.utils.update_web_specification_description_options(
        frm,
        descriptions
    );
}