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
		// Metactical Customization: set after refresh (not onload) so this overrides
		// erpnext's core onload handler, which applies a generic Warehouse query to
		// set_warehouse/accepted_warehouse via erpnext.queries.setup_queries
		frm.set_query("set_warehouse", function() {
			return {
				query: "metactical.custom_scripts.purchase_receipt.purchase_receipt.get_accepted_warehouse",
				filters: {"user": frappe.session.user}
			};
		});
		// Metactical Customization: the item row's "Accepted Warehouse" field's
		// actual fieldname is "warehouse" (label is "Accepted Warehouse")
		frm.set_query("warehouse", "items", function() {
			return {
				query: "metactical.custom_scripts.purchase_receipt.purchase_receipt.get_accepted_warehouse",
				filters: {"user": frappe.session.user}
			};
		});

		frm.add_custom_button("Print", function() {
			var print_format = "PR Report V5";
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
	}
});
