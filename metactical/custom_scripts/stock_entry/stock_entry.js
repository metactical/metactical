frappe.ui.form.on('Stock Entry', {
	refresh: function(frm){
		if (frm.doc.docstatus === 1) {
			if (!frm.doc.add_to_transit && frm.doc.purpose=='Material Transfer' && frm.doc.per_transferred < 100) {
				frm.add_custom_button('Move Stock', function() {
					frappe.model.open_mapped_doc({
						method: "erpnext.stock.doctype.stock_entry.stock_entry.make_stock_in_entry",
						frm: frm
					})
				});
			}
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
		
		if(this.frm.doc.__islocal == 1){
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
	}
});
$.extend(cur_frm.cscript, new erpnext.stock.StockEntry({frm: cur_frm}));
