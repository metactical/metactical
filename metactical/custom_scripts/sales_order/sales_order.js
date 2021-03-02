frappe.ui.form.on('Sales Order', {
	refresh: function(frm){
		//Clear update qty and rate button
		console.log(frm);
		if(frm.doc.docstatus === 1 && frm.doc.status !== 'Closed'
			&& flt(frm.doc.per_delivered, 6) < 100 && flt(frm.doc.per_billed, 6) < 100) {
			frm.clear_custom_buttons();
		}
	}
});
