// Copyright (c) 2025, Techlift Technologies and contributors
// For license information, please see license.txt

frappe.ui.form.on('SB Tag', {
	refresh: function (frm) {
        metactical.utils.load_website_specifications_options(frm);
    }, 
});

frappe.ui.form.on("MT Item Website Specification", {
	label: function (frm, cdt, cdn) {
		metactical.utils.load_website_specifications_options(frm);
	},
})
