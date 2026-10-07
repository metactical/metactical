// Copyright (c) 2026, Storebuilder Commerce Inc and contributors
// For license information, please see license.txt

// Jobs are created and run from the Item Merge page; the form is a read-only record of one.
frappe.ui.form.on("Item Merge Job", {
	refresh(frm) {
		frm.disable_save();
		frm.add_custom_button(__("Open in Item Merge"), () => {
			frappe.set_route("item-merge", "jobs", frm.doc.name);
		});
	},
});
