frappe.ui.form.on('Pick List', {
	refresh: function(frm){
		console.log(frm);
	},
	
	on_submit: function(frm){
		var new_url = window.location.origin + "/printview?doctype=Pick%20List&name=" + frm.doc.name + "&trigger_print=1&format=Pick%20List%204*6&no_letterhead=0&_lang=en"
		//http://frappe-metactical/printview?doctype=Pick%20List&name=STO-PICK-2021-00002&trigger_print=1&format=Pick%20List%204*6&no_letterhead=0&_lang=en
		//var new_url = `${window.location.origin}/itemsearch?searchtext=${search_text}`
		window.open(new_url)
	}
});
