// Copyright (c) 2017, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Item Merge Settings", {
	refresh(frm) {
		set_field_options(frm);
	},
});

// Both tables pick a field off the Item doctype, so both get the same option list. Anything that
// cannot meaningfully be carried between two items is left out: layout fields, tables, buttons,
// read-only fields and anything Frappe already marks no_copy.
function set_field_options(frm) {
	const EXCLUDED = [
		"HTML",
		"Section Break",
		"Column Break",
		"Button",
		"Read Only",
		"Table",
		"Table MultiSelect",
	];

	frappe.model.with_doctype("Item", () => {
		const allow_fields = frappe
			.get_meta("Item")
			.fields.filter((d) => !in_list(EXCLUDED, d.fieldtype) && !d.no_copy)
			.map((d) => ({ label: `${__(d.label)} (${d.fieldname})`, value: d.fieldname }));

		if (!allow_fields.length) {
			allow_fields.push({ label: __("No additional fields available"), value: "" });
		}

		["fields_to_overwrite", "fields_to_copy"].forEach((table) => {
			frm.fields_dict[table]?.grid.update_docfield_property("field_name", "options", allow_fields);
		});
	});
}

