// Copyright (c) 2022, Techlift Technologies and contributors
// For license information, please see license.txt

frappe.ui.form.on('Employee Sign Up', {
	onload: function(frm){
		const role_area = $('<div class="role-editor">')
					.appendTo(frm.fields_dict.roles_html.wrapper);

				frm.roles_editor = new frappe.RoleEditor(role_area, frm, frm.doc.role_profile_name ? 1 : 0);
	}
});
