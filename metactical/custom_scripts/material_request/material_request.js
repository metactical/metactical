frappe.ui.form.on('Material Request', {
	get_item_data: function(frm, item, overwrite_warehouse=false) {
		// Metactical customizatino: Prevent overwriting of target warehouse
		overwrite_warehouse = false;
		
		if (item && !item.item_code) { return; }
		frm.call({
			method: "erpnext.stock.get_item_details.get_item_details",
			child: item,
			args: {
				args: {
					item_code: item.item_code,
					warehouse: item.warehouse,
					from_warehouse: item.from_warehouse,
					doctype: frm.doc.doctype,
					buying_price_list: frappe.defaults.get_default('buying_price_list'),
					currency: frappe.defaults.get_default('Currency'),
					name: frm.doc.name,
					qty: item.qty || 1,
					stock_qty: item.stock_qty,
					company: frm.doc.company,
					conversion_rate: 1,
					material_request_type: frm.doc.material_request_type,
					plc_conversion_rate: 1,
					rate: item.rate,
					uom: item.uom,
					conversion_factor: item.conversion_factor
				},
				overwrite_warehouse: overwrite_warehouse
			},
			callback: function(r) {
				const d = item;
				const qty_fields = ['actual_qty', 'projected_qty', 'min_order_qty'];
				
				if(!r.exc) {
					$.each(r.message, function(k, v) {
						if(!d[k] || in_list(qty_fields, k)) d[k] = v;
					});
				}
				
				//For default supplier
				d.ais_default_supplier = r.message['supplier'];
			}
		});
	}
});
