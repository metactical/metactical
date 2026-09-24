// Copyright (c) 2026, Metactical and contributors
// For license information, please see license.txt

frappe.ui.form.on("Zoho Books Settings", {
	generate_tokens(frm) {
		if (!frm.doc.authorization_code) {
			frappe.msgprint(__("Please enter the Authorization Code (Grant Token) first."));
			return;
		}
		frappe.call({
			method: "metactical.metactical.doctype.zoho_books_settings.zoho_books_settings.generate_tokens",
			freeze: true,
			freeze_message: __("Exchanging grant token with Zoho..."),
			callback: (r) => {
				if (!r.exc) {
					frappe.show_alert({ message: r.message, indicator: "green" });
					frm.reload_doc();
				}
			},
			error: () => {
				// A grant token is single-use; clear it so a spent code can't be
				// resubmitted. The user must paste a fresh code to retry.
				frm.set_value("authorization_code", "");
				frm.save().then(() => {
					frappe.msgprint(
						__("The grant token was rejected and has been cleared. Generate a fresh code in the Zoho API console, paste it, and try again.")
					);
				});
			},
		});
	},

	fetch_credit_cards(frm) {
		frappe.call({
			method: "metactical.metactical.doctype.zoho_books_settings.zoho_books_settings.fetch_credit_cards",
			freeze: true,
			freeze_message: __("Fetching credit cards from Zoho Books..."),
			callback: (r) => {
				if (!r.exc) {
					frappe.show_alert({ message: r.message, indicator: "green" });
					frm.reload_doc();
				}
			},
		});
	},
});
