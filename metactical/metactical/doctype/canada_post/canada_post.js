// Copyright (c) 2022, Techlift Technologies and contributors
// For license information, please see license.txt

frappe.ui.form.on('Canada Post', {
	get_manifest: function(frm){
		frm.call({
			method: "metactical.metactical.doctype.canada_post.canada_post.get_manifest",
			args: {},
			freeze: true,
			callback: function(ret){
				console.log(ret);
			}
		});
	}
});
