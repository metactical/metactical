frappe.ui.form.on("Packing Slip", {
	refresh: function(frm){
		frm.set_query("custom_neb_parcel_template", function() {
			return {
				filters: {
					"custom_disabled": 0
				}
			};
		});
	}
});