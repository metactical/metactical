frappe.ui.form.on('Stock Entry', {
	refresh: function(frm){
		if (frm.doc.docstatus === 1) {
			if (!frm.doc.add_to_transit && frm.doc.purpose=='Material Transfer' && frm.doc.per_transferred < 100) {
				var is_active = false
				for(let i in frm.doc.items){
					var row = frm.doc.items[i];
					if(row.t_warehouse.includes('Active')){
						is_active = true
						break;
					}
				}
				
				if(!is_active){
					frm.add_custom_button('Move Stock', function() {
						frappe.model.open_mapped_doc({
							method: "erpnext.stock.doctype.stock_entry.stock_entry.make_stock_in_entry",
							frm: frm
						})
					});
				}
			}
		}
	},
	
	onload_post_render: function(frm){
		frm.$wrapper.on('keypress', function(event){
			if(event.keyCode == 13)
			{
				return false;
			}
		});
	},
	
	on_submit: function(frm){
		if(frm.doc.ais_from_report && frm.doc.ais_from_report == 1){
			var print_url = window.location.origin + "/printview?doctype=Stock%20Entry&name=" + frm.doc.name + "&trigger_print=1&format=STE%20Pick%20List&no_letterhead=0&_lang=en";	
			window.open(print_url)
		}
	}
})

erpnext.stock.StockEntry = erpnext.stock.StockEntry.extend({
	onload: function(frm){
		var me = this;
		frappe.after_ajax(function(){
			me.frm.set_query("from_warehouse", function(){
				return {
					query: "metactical.custom_scripts.stock_entry.stock_entry.get_permitted_source",
					filters: {"user": frappe.session.user}
				};
			});
			
			me.frm.set_query("to_warehouse", function(){
				return {
					query: "metactical.custom_scripts.stock_entry.stock_entry.get_permitted_target",
					filters: {"user": frappe.session.user}
				};
			});
			
			me.frm.set_query("s_warehouse", "items", function(){
				return {
					query: "metactical.custom_scripts.stock_entry.stock_entry.get_permitted_source",
					filters: {"user": frappe.session.user}
				};
			});
			
			me.frm.set_query("t_warehouse", "items", function(){
				return {
					query: "metactical.custom_scripts.stock_entry.stock_entry.get_permitted_target",
					filters: {"user": frappe.session.user}
				};
			});
		});
		
		if(this.frm.doc.__islocal == 1 && !this.frm.doc.outgoing_stock_entry){
			console.log("In here");
			frappe.call({
				method: "metactical.custom_scripts.stock_entry.stock_entry.get_default_transit",
				args: {
					"user": frappe.session.user
				},
				freeze: true,
				callback: function(ret){
					if(ret.message != undefined){
						frappe.after_ajax(() => {
								setTimeout(() => {
									me.frm.set_value('add_to_transit', ret.message)
								}, 1000);
						});
					}
				}
			});
		}
	},
	
	ais_scan_to_confirm: function(){
		let transaction_controller= new erpnext.TransactionController({frm:this.frm});
		transaction_controller.ais_scan_to_confirm();
	}
});
$.extend(cur_frm.cscript, new erpnext.stock.StockEntry({frm: cur_frm}));
