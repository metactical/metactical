// Copyright (c) 2026, Storebuilder Commerce Inc and contributors
// For license information, please see license.txt

frappe.ui.form.on("S3 Settings", {
	refresh(frm) {
		frm.__test_btn = frm.add_custom_button(__("Test Connection"), () => {
			if (frm.doc.nat_disabled) return;
			if (frm.is_dirty()) {
				frappe.show_alert({ message: __("Save your changes first to test them."), indicator: "orange" });
			}
			frappe.dom.freeze(__("Testing S3 connection…"));
			frappe.call({
				method: "metactical.metactical.page.s3_uploader.s3_uploader.test_connection",
				callback: (r) => {
					frappe.dom.unfreeze();
					const msg = r.message || {};
					frappe.msgprint({
						title: msg.success ? __("Success") : __("Connection failed"),
						message: msg.message,
						indicator: msg.success ? "green" : "red",
					});
				},
				error: () => frappe.dom.unfreeze(),
			});
		});
		set_test_button_state(frm);
	},

	// Re-evaluate the button when the Disabled flag is toggled.
	nat_disabled(frm) {
		set_test_button_state(frm);
	},
});

// Gray out + block the Test Connection button while S3 Settings is disabled.
function set_test_button_state(frm) {
	const btn = frm.__test_btn;
	if (!btn) return;
	const disabled = !!frm.doc.nat_disabled;
	btn.prop("disabled", disabled).css({
		opacity: disabled ? 0.5 : 1,
		"pointer-events": disabled ? "none" : "",
	});
}
