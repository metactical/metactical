frappe.ui.form.on('Employee',{
	validate: function(frm){
		if(frm.doc.ais_bank_transit && isNaN(frm.doc.ais_bank_transit)){
			frappe.validated = false;
			frappe.throw("Bank Transit value can only be a number");
		}
		else if (frm.doc.ais_bank_institution && isNaN(frm.doc.ais_bank_institution)){
			frappe.validated = false;
			frappe.throw("Bank Institution value can only be a number");
		}
	}
});
