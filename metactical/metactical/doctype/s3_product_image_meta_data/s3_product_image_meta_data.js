// Copyright (c) 2026, Storebuilder Commerce Inc and contributors
// For license information, please see license.txt

frappe.ui.form.on("S3 Product Image Meta Data", {
	refresh(frm) {
		frm.add_custom_button(__("Download JSON"), () => {
			frappe.call({
				method: "metactical.metactical.page.s3_uploader.s3_uploader.build_export_json",
				args: { names: JSON.stringify([frm.doc.name]) },
				freeze: true,
				freeze_message: __("Building JSON…"),
				callback: (r) => {
					if (!r.message) return;
					const json = JSON.stringify(r.message, null, 2);
					const blob = new Blob([json], { type: "application/json" });
					const url = URL.createObjectURL(blob);
					const link = document.createElement("a");
					link.href = url;
					link.download = `${frm.doc.name}.json`;
					document.body.appendChild(link);
					link.click();
					document.body.removeChild(link);
					URL.revokeObjectURL(url);
				},
			});
		});
	},
});
