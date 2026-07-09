// Copyright (c) 2026, Storebuilder Commerce Inc and contributors
// For license information, please see license.txt

frappe.ui.form.on("Restock Email Log", {
	refresh(frm) {
		if (frm.is_new()) {
			return;
		}

		// Add the "Send Email" button. Disable it when this email has already been
		// sent, or when notifications are turned off in Restock Notification Settings.
		frappe.db
			.get_single_value("Restock Notification Settings", "send_notification")
			.then((send_notification) => {
				const btn = frm.add_custom_button(__("Send Email"), () => open_send_dialog(frm));
				if (frm.doc.status === "Sent") {
					btn.prop("disabled", true).attr("title", __("This email has already been sent"));
				} else if (!send_notification) {
					btn.prop("disabled", true).attr(
						"title",
						__("Sending notifications is disabled in Restock Notification Settings")
					);
				}
			});
	},
});

function open_send_dialog(frm) {
	frappe.call({
		method: "metactical.custom_scripts.utils.restock_notification.get_email_preview",
		args: { email_log: frm.doc.name },
		freeze: true,
		callback: (r) => {
			const data = r.message || {};

			if (!data.can_send) {
				frappe.msgprint(
					__("Sending notifications is disabled in Restock Notification Settings.")
				);
				return;
			}
			if (!data.has_template) {
				frappe.msgprint(
					__("No email template is configured for lead source {0}.", [
						frm.doc.lead_source || "—",
					])
				);
				return;
			}

			const dialog = new frappe.ui.Dialog({
				title: __("Send Restock Email"),
				fields: [
					{
						fieldtype: "Data",
						fieldname: "recipient",
						label: __("To"),
						read_only: 1,
						default: data.recipient,
					},
					{
						fieldtype: "Data",
						fieldname: "subject",
						label: __("Subject"),
						read_only: 1,
						default: data.subject,
					},
					{ fieldtype: "HTML", fieldname: "preview", label: __("Email") },
				],
				primary_action_label: __("Send"),
				primary_action() {
					frappe.call({
						method: "metactical.custom_scripts.utils.restock_notification.send_email",
						args: { email_log: frm.doc.name },
						freeze: true,
						freeze_message: __("Sending..."),
						callback: () => {
							frappe.show_alert(
								{ message: __("Restock email queued"), indicator: "green" },
								5
							);
							dialog.hide();
							frm.reload_doc();
						},
					});
				},
				secondary_action_label: __("Cancel"),
				secondary_action() {
					dialog.hide();
				},
			});

			dialog.fields_dict.preview.$wrapper.html(
				`<div class="restock-email-preview" style="border:1px solid var(--border-color);
					padding:12px;border-radius:6px;max-height:420px;overflow:auto;">
					${data.message || ""}
				</div>`
			);
			dialog.show();
		},
	});
}
