// Copyright (c) 2024, Techlift Technologies and contributors
// For license information, please see license.txt
var total_queues_completed = 0;

frappe.ui.form.on('Trello Data Import', {
	refresh: function(frm) {
		
	},
	start_import: function(frm){
		if (frm.__unsaved) {
			frm.save();
		}
		
		setTimeout(() => {
			frappe.call({
				method: "metactical.metactical.doctype.trello_data_import.trello_data_import.import_csv",
				args: {
					"doc_name": frm.doc.name
				},
				callback: function(r){
					frappe.show_alert(r.message);
				}
			});
		}, 1000);

		
	}
});

frappe.realtime.on("trello_data_import", function(data){
	var message = "Total Batches Imported: "+ (++total_queues_completed);
	frappe.show_alert(message);
});