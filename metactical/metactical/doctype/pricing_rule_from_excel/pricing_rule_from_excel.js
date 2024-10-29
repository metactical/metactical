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
	download_template(frm) {
		var dialog = new frappe.ui.Dialog({
			title: __("Download Template"),
			fields: [
				{
					fieldname: "price_list",
					label: __("Price List"),
					fieldtype: "Link",
					options: "Price List",
					reqd: 1
				},
				{
					fieldname: "export_type",
					label: __("Export Type"),
					fieldtype: "Select",
					options: [
						{ value: "Blank", label: __("Blank Template") },
						{ value: "All", label: __("All Records") },
						{ value: "Five", label: __("First Five Records") },
					],
					default: "Blank",
				}
			],
			primary_action_label: __("Download"),
			primary_action: (values) => {
				let method = "/api/method/metactical.metactical.doctype.pricing_rule_from_excel.pricing_rule_from_excel.download_template";

				open_url_post(method, {
					price_list: values.price_list,
					export_type: values.export_type,
					import_based_on: frm.doc.import_based_on,
				});

				dialog.hide();
			}
		});

		dialog.show();
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
