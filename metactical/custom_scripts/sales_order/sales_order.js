frappe.ui.form.on('Sales Order', {
	refresh: function(frm){
		//Clear update qty and rate button
		console.log(frm);
		if(frm.doc.docstatus === 1 && frm.doc.status !== 'Closed'
			&& flt(frm.doc.per_delivered, 6) < 100 && flt(frm.doc.per_billed, 6) < 100) {
			frm.clear_custom_buttons();
		}
		
		setTimeout(() => {
			frm.remove_custom_button("Pick List", 'Create'); 
			frm.add_custom_button(__('Pick List'), () => frm.events.create_pick_list_custom(), __("Create"));
		}, 10);
	},
	
	create_pick_list_custom() {
		frappe.model.open_mapped_doc({
			method: "metactical.custom_scripts.pick_list.pick_list.create_pick_list",
			frm: cur_frm
		})
	}
});
