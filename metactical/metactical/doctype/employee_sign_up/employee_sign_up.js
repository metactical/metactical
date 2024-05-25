// Copyright (c) 2022, Techlift Technologies and contributors
// For license information, please see license.txt

frappe.ui.form.on('Employee Sign Up', {
	onload: function(frm){
		const role_area = $('<div class="role-editor">')
					.appendTo(frm.fields_dict.roles_html.wrapper);

				frm.roles_editor = new frappe.RoleEditor(role_area, frm, frm.doc.role_profile_name ? 1 : 0);
	},
	bank_account_no: function(frm){
		if (frm.doc.bank_account_no.length > 12){
			show_tooltip('bank_account_no', 'Account number should be at most 12 digits');
		}
		else if (frm.doc.bank_account_no.length < 7){
			show_tooltip('bank_account_no', 'Account number should be at least 7 digits');
		}
		else{
			$('[data-fieldname="bank_account_no"]').removeAttr('data-original-title').tooltip('hide');
	
		}
	},
	bank_transit_no: function(frm){
		if(frm.doc.bank_transit_no.length > 5){
			show_tooltip('bank_transit_no', 'Transit number should be at most 5 digits');
		}
		else if (frm.doc.bank_transit_no.length < 5){
			$('[data-fieldname="bank_transit_no"]').removeAttr('data-original-title').tooltip('hide');
		}
		
		if (!/^\d+$/.test(frm.doc.bank_transit_no)){
			show_tooltip("bank_transit_no", "Transit number should be a number")
		}
	}
});

function show_tooltip(fieldname, message){
	$('input[data-fieldname="'+fieldname+'"]').attr('data-original-title', message).tooltip('show');
}
// dummy commit