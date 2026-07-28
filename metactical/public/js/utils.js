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
metactical.utils.get_descriptions_dict = function (r) {
    var descriptions = {};
    r.forEach((row) => {
        if (!descriptions[row.parent]) {
            descriptions[row.parent] = [];
        }
        descriptions[row.parent].push(row.description);
    });
    return descriptions; // just build and return, no side effects
};

metactical.utils.load_website_specifications_options = function (frm) {
    if (!frm.doc.neb_website_specifications || !frm.doc.neb_website_specifications.length) {
        return;
    }
    var labels = frm.doc.neb_website_specifications.map((row) => row.label);
    frappe.call({
        method: "metactical.custom_scripts.item.item.get_website_specification_description_options",
        args: { labels: labels },
        callback: function (r) {
            var descriptions = metactical.utils.get_descriptions_dict(r.message);
            metactical.utils.update_web_specification_description_options(frm, descriptions);
        },
    });
};

metactical.utils.update_web_specification_description_options = function (frm, descriptions_obj) {
    if (!descriptions_obj) return;

    var grid = frm.fields_dict["neb_website_specifications"].grid; // use frm, not cur_frm
    frm.doc.neb_website_specifications.forEach((row) => {
        var grid_row = grid.grid_rows_by_docname[row.name]; // keyed by docname, not position
        if (!grid_row) return;

        var options = descriptions_obj[row.label] ? descriptions_obj[row.label].slice() : [];
        if (!row.mandatory) {
            options.unshift("");
        }
        var field = frappe.utils.filter_dict(grid_row.docfields, { fieldname: "description" })[0];
        if (field) field.options = options;
    });

    frm.refresh_field("neb_website_specifications");
};