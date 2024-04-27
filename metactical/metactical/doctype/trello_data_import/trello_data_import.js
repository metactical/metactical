// Copyright (c) 2024, Techlift Technologies and contributors
// For license information, please see license.txt
<<<<<<< HEAD

=======
>>>>>>> 3dada9aa9d18597fd4f3fd4b5ab2ad9909bed0e6
var total_queues_completed = 0;

frappe.ui.form.on('Trello Data Import', {
	refresh: function(frm) {
		
	},
	start_import: function(frm){
<<<<<<< HEAD
		// frm.save();

=======
		if (frm.__unsaved) {
			frm.save();
		}
		
>>>>>>> 3dada9aa9d18597fd4f3fd4b5ab2ad9909bed0e6
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
<<<<<<< HEAD
	frappe.show_alert('Queue ' + (++total_queues_completed) + ' completed');
=======
	var message = "Total Batches Imported: "+ (++total_queues_completed);
	frappe.show_alert(message);
>>>>>>> 3dada9aa9d18597fd4f3fd4b5ab2ad9909bed0e6
});