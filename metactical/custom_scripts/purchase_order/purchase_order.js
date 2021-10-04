erpnext.buying.CustomPurchaseOrderController = erpnext.buying.PurchaseOrderController.extend({
	onload: function(doc, cdt, cdn){
		console.log("custom load");
		if(this.frm.get_field('shipping_address')) {
			this.frm.set_query("shipping_address", function() {
				if(me.frm.doc.customer) {
					return {
						query: 'metactical.custom_scripts.purchase_order.purchase_order.shipping_address_query',
						filters: { link_doctype: 'Customer', link_name: me.frm.doc.customer, company: me.frm.doc.company  }
					};
				} else
					return erpnext.queries.company_address_query(me.frm.doc)
			});
		}
		/*frm.set_query("shipping_address", function() {
			if(frm.doc.customer) {
				return {
					query: 'metactical.custom_scripts.purchase_order.purchase_order.shipping_address_query',
					filters: { link_doctype: 'Customer', link_name: frm.doc.customer, company: frm.doc.company }
				};
			} else
				return erpnext.queries.company_address_query(frm.doc)
		});*/
	}
})
// for backward compatibility: combine new and previous states
$.extend(cur_frm.cscript, new erpnext.buying.CustomPurchaseOrderController({frm: cur_frm}));
