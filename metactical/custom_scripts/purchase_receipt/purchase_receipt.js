frappe.ui.form.on("Purchase Receipt", {
	onload_post_render: function(frm){
		frm.$wrapper.on('keypress', function(event){
			if(event.keyCode == 13)
			{
				return false;
			}
		});
	},
	refresh: function(frm) {
		frm.add_custom_button("Print", function() {
			var print_format = "Purchase Receipt Barcode - V2";
			var w = window.open(frappe.urllib.get_full_url("/api/method/frappe.utils.print_format.download_pdf?"
				+ "doctype=" + encodeURIComponent("Purchase Receipt")
				+ "&name=" + encodeURIComponent(frm.doc.name)
				+ "&format=" + encodeURIComponent(print_format)
				+ "&no_letterhead=0"
			));
			if(!w) {
				frappe.msgprint(__("Please enable pop-ups")); return;
			}
		});

		// frm.add_custom_button("Print", function() {
		// 	var print_format = "Purchase Receipt Barcode - V2";
		// 	frappe.call({
		// 		method: "metactical.custom_scripts.purchase_receipt.purchase_receipt.get_print_format",
		// 		args: {
		// 			"docname": frm.doc.name,
		// 		},
		// 		callback: function(r) {
		// 			var w = window.open();
		// 			w.document.write(r.message);
		// 			w.print();
		// 		}
		// 	});
		// });
	}
});
