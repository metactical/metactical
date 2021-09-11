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
	}
});
$.extend(cur_frm.cscript, new erpnext.stock.StockEntry({frm: cur_frm}));
