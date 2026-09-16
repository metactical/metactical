// Copyright (c) 2017, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Item Merge Settings", {
	refresh(frm) {
		set_field_options(frm);
		frm.add_custom_button(__("Test Metabase connection"), () => test_metabase(frm));
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

function test_metabase(frm) {
	if (frm.is_dirty()) {
		frappe.msgprint({
			title: __("Metabase"),
			message: __("Save the settings first, then test the connection."),
			indicator: "orange",
		});
		return;
	}
	frappe.call({
		method: "metactical.metactical.doctype.item_merge_settings.item_merge_settings.test_metabase_connection",
		freeze: true,
		freeze_message: __("Asking Metabase…"),
		callback: ({ message }) => {
			const rows = (message || [])
				.map((r) => {
					const state = r.ok
						? `<span class="indicator-pill green">ok</span> ${frappe.utils.escape_html(String(r.products ?? ""))} product(s)`
						: `<span class="indicator-pill red">failed</span> ${frappe.utils.escape_html(r.error || "")}`;
					return `<tr><td>${frappe.utils.escape_html(r.price_list || "")}</td>
						<td>${frappe.utils.escape_html(String(r.database_id))}</td><td>${state}</td></tr>`;
				})
				.join("");
			frappe.msgprint({
				title: __("Metabase connection"),
				message: `<table class="table table-bordered"><thead><tr>
					<th>${__("Price List")}</th><th>${__("Database")}</th><th>${__("Result")}</th>
					</tr></thead><tbody>${rows}</tbody></table>`,
				indicator: (message || []).every((r) => r.ok) ? "green" : "orange",
			});
		},
	});
}
