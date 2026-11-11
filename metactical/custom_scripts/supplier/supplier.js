// PO V3 Ordering: the CC / BCC addresses as pills (public/js/email_pills.js), and
// the Main Signature user by name
frappe.ui.form.on("Supplier", {
	refresh(frm) {
		["po3_cc_email", "nat_po3_bcc_email"].forEach((f) => metactical.email_pills.render(frm, f));
		metactical.utils.show_user_full_name(frm, "nat_po3_signature_user");
	},
	po3_cc_email(frm) {
		metactical.email_pills.render(frm, "po3_cc_email");
	},
	nat_po3_bcc_email(frm) {
		metactical.email_pills.render(frm, "nat_po3_bcc_email");
	},
	nat_po3_signature_user(frm) {
		metactical.utils.show_user_full_name(frm, "nat_po3_signature_user");
	},
});
