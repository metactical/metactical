// Copyright (c) 2026, Techlift Technologies and contributors
// For license information, please see license.txt

frappe.ui.form.on('Supplier Import Profile', {
	setup: function(frm) {
		// Searchable list of the target table's fields, by label
		const field_query = (doc, cdt, cdn) => ({
			query: 'metactical.metactical.doctype.supplier_import_profile.supplier_import_profile.search_target_fields',
			params: {target_doctype: locals[cdt][cdn].target_doctype},
		});
		frm.set_query('target_field', 'mappings', field_query);
	}
});

frappe.ui.form.on('Supplier Import Profile Mapping', {
	target_doctype: function(frm, cdt, cdn) {
		frappe.model.set_value(cdt, cdn, {target_field: '', target_field_label: ''});
	},

	form_render: function(frm, cdt, cdn) {
		// The label is only for the table view; in the row editor the search box already says it
		const row = frm.fields_dict.mappings.grid.get_row(cdn);
		row.grid_form.fields_dict.target_field_label.$wrapper.hide();
	}
});
