// Copyright (c) 2017, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Item Merge Settings", {
	refresh: function (frm) {
		const allow_fields = [];

		const exclude_field_types = ["HTML", "Section Break", "Column Break", "Button", "Read Only", "Table", "Table MultiSelect"];

		frappe.model.with_doctype("Item", () => {
			const field_label_map = {};
			frappe.get_meta("Item").fields.forEach((d) => {
				field_label_map[d.fieldname] = __(d.label) + ` (${d.fieldname})`;

				if (
					!in_list(exclude_field_types, d.fieldtype) &&
					!d.no_copy
				) {
					allow_fields.push({
						label: field_label_map[d.fieldname],
						value: d.fieldname,
					});
				}
			});

			if (allow_fields.length == 0) {
				allow_fields.push({
					label: __("No additional fields available"),
					value: "",
				});
			}

			frm.fields_dict.fields_to_overwrite.grid.update_docfield_property("field_name", "options", allow_fields);
			frm.fields_dict.fields_to_copy.grid.update_docfield_property("field_name", "options", allow_fields);
		});
	},
});
