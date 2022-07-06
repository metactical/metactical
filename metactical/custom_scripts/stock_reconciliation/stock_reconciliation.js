frappe.ui.form.on('Stock Reconciliation', {
	onload: function(frm){
		//Wait one secondto make sure the other query is set so this replaces it
		setTimeout(() => {
			frm.set_query('warehouse', 'items', function(){
				return {
					query: "metactical.metactical.doctype.cycle_count_v2.cycle_count_v2.get_permitted_warehouses",
					filters: {'user': frappe.session.user}
				};
			});
		}, 1000);
	}
});
