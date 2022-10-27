frappe.ui.form.on("Purchase Receipt", {
	onload_post_render: function(frm){
		frm.$wrapper.on('keypress', function(event){
			if(event.keyCode == 13)
			{
				return false;
			}
		});
	}
});
