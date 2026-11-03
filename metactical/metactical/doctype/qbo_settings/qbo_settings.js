// Copyright (c) 2026, Storebuilder Commerce Inc and contributors
// For license information, please see license.txt

frappe.ui.form.on("QBO Settings", {
	connect(frm) {
		if (!frm.doc.client_id || !frm.doc.client_secret || !frm.doc.redirect_uri) {
			frappe.msgprint(__("Please fill in Client ID, Client Secret, and Redirect URI first, then save."));
			return;
		}
		frappe.call({
			method: "metactical.metactical.doctype.qbo_settings.qbo_settings.get_auth_url",
			freeze: true,
			freeze_message: __("Building authorization URL..."),
			callback(r) {
				if (r.exc || !r.message) return;
				const popup = window.open(r.message, "qbo_oauth", "width=600,height=700");
				if (!popup) {
					frappe.msgprint(
						__("Could not open popup. Please allow popups for this site, or open this URL manually:") +
						`<br><a href="${r.message}" target="_blank">${r.message}</a>`
					);
					return;
				}
				// Poll until the popup closes (authorization complete or user dismissed).
				const timer = setInterval(() => {
					if (popup.closed) {
						clearInterval(timer);
						frm.reload_doc();
					}
				}, 1000);
			},
		});
	},

	fetch_bank_accounts(frm) {
		frm.save().then(() => {
			frappe.call({
				method: "metactical.metactical.doctype.qbo_settings.qbo_settings.fetch_bank_accounts",
				freeze: true,
				freeze_message: __("Fetching bank accounts from QuickBooks..."),
				callback(r) {
					if (!r.exc) {
						frappe.show_alert({ message: r.message, indicator: "green" });
						frm.reload_doc();
					}
				},
			});
		});
	},

	fetch_bank_transactions(frm) {
		frm.save().then(() => {
			frappe.call({
				method: "metactical.metactical.doctype.qbo_settings.qbo_settings.fetch_bank_transactions",
				freeze: true,
				freeze_message: __("Fetching bank transactions from QuickBooks..."),
				callback(r) {
					if (!r.exc) {
						frappe.show_alert({ message: r.message, indicator: "green" });
						frm.reload_doc();
					}
				},
			});
		});
	},

	disconnect(frm) {
		frappe.confirm(
			__("Disconnect from QuickBooks? Stored tokens will be removed."),
			() => {
				frappe.call({
					method: "metactical.metactical.doctype.qbo_settings.qbo_settings.disconnect",
					freeze: true,
					callback(r) {
						if (!r.exc) {
							frappe.show_alert({ message: r.message, indicator: "orange" });
							frm.reload_doc();
						}
					},
				});
			}
		);
	},
});
