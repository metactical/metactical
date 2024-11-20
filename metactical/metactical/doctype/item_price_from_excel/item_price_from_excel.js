// Copyright (c) 2024, Techlift Technologies and contributors
// For license information, please see license.txt

frappe.ui.form.on('Item Price From Excel', {
	refresh: function(frm) {
		frm.add_custom_button(__('Import'), function() {
			frappe.call({
				method: "runserverobj",
				freeze: true,
				args: {
					docs: frm.doc,
					method: "submit"
				},
				callback: function(r) {
					frm.reload_doc();
				}
			});
		})
	}
});
