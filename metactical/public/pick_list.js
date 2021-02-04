frappe.ui.form.on('Sales Order', {
	refresh: function(frm){
		setTimeout(() => {
			frm.remove_custom_button("Pick List", 'Create'); 
			frm.add_custom_button(__('Pick List'), () => frm.events.create_pick_list_custom(), __("Create"));
		}, 10);
	},
	
	create_pick_list_custom() {
		frappe.model.open_mapped_doc({
			method: "metactical.pick_list.create_pick_list",
			frm: cur_frm
		})
	}
});
