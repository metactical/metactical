// Copyright (c) 2025, Techlift Technologies and contributors
// For license information, please see license.txt

frappe.ui.form.on('POS User Settings', {
	refresh: function(frm) {
		if (frappe.user.has_role('System Manager')) {
			frm.add_custom_button(__('Show Password'), function() {
				frm.call({
					method: 'metactical.custom_scripts.utils.metactical_utils.get_password',
					args: { doc: frm.doc },
					freeze: true,
					callback: function(r) {
						frappe.msgprint(r.message);
					}
				});
			});
		}
	}
});
