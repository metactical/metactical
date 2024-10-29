// Copyright (c) 2024, Techlift Technologies and contributors
// For license information, please see license.txt

frappe.ui.form.on('Pricing Rule From Excel', {
	refresh: function(frm) {
		if (!frm.doc.__islocal) {
			frm.doc.preview_data = null;
			frappe.call({
				doc: frm.doc,
				method: "get_preview_from_template",
				args: {
					template: frm.doc.template,
					template_options: frm.doc.template_options,
				},
				callback: (r) => {
					frm.doc.preview_data = r.message;
					frm.events.show_import_preview(frm, frm.doc.preview_data);
				},
			});
		}
	},
	show_import_preview(frm, preview_data) {
		let import_log = preview_data.import_log;

		if (frm.import_preview && frm.import_preview.doctype === frm.doc.reference_doctype) {
			frm.import_preview.preview_data = preview_data;
			frm.import_preview.import_log = import_log;
			frm.import_preview.refresh();
			return;
		}

		frappe.require("data_import_tools.bundle.js", () => {
			frm.import_preview = new frappe.data_import.ImportPreview({
				wrapper: frm.get_field("import_preview").$wrapper,
				doctype: frm.doc.doctype,
				preview_data,
				import_log,
				frm,
				events: {
					remap_column(changed_map) {
						let template_options = JSON.parse(frm.doc.template_options || "{}");
						template_options.column_to_field_map =
							template_options.column_to_field_map || {};
						Object.assign(template_options.column_to_field_map, changed_map);
						frm.set_value("template_options", JSON.stringify(template_options));
						frm.save().then(() => frm.trigger("import_file"));
					},
				},
			});
		});
	},
});
