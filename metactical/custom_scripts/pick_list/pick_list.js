frappe.ui.form.on('Pick List', {
	refresh: function(frm){
		console.log(frm);
		
		//Code for custom cancel button that saves cancel reason first
		if(frm.doc.docstatus == 1){
			frm.page.clear_secondary_action();
			frm.page.set_secondary_action(__("Cancel"), function(frm) {
				cur_frm.events.before_cancel_event();
			});
		}
	},
	
	on_submit: function(frm){
		var new_url = window.location.origin + "/printview?doctype=Pick%20List&name=" + frm.doc.name + "&trigger_print=1&format=Pick%20List%204*6&no_letterhead=0&_lang=en"
		window.open(new_url)
	},
	
	before_cancel_event: function(frm){
		frappe.prompt([
			{'fieldname': 'cancel_reason', 'fieldtype': 'Small Text', 'label': 'Enter Reason', 'reqd': 1}
		],
		function(values){
			frappe.call({
				'method': 'metactical.pick_list.save_cancel_reason',
				'args': {
					'docname': cur_frm.docname,
					'cancel_reason': values.cancel_reason
				},
				'callback': function(r){
					cur_frm.savecancel();
				}
			});
		},
		'Please reason for cancellation.',
		'Cancel'
		)
	}
});
