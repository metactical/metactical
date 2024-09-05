frappe.ui.form.on('Material Request', {
	refresh: function(frm) {
		if (frm.doc.docstatus == 0) {
			get_quantities_on_hand(frm);
		}
	},
	onload: function(frm) {
		frappe.after_ajax(function(){
			frm.set_query("set_warehouse", function(doc){
				return {
					query: "metactical.custom_scripts.material_request.material_request.get_target_warehouse",
					filters: {"user": frappe.session.user}
				}
			});

			frm.set_query( "warehouse", "items", function(){
				return {
					query: "metactical.custom_scripts.material_request.material_request.get_target_warehouse",
					filters: {"user": frappe.session.user}
				}
			});
		});
	},

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
	},
	
});

frappe.ui.form.on('Material Request Item', {
	qty: function(frm, cdt, cdn) {
		var row = locals[cdt][cdn];
		if (row.qty > row.qoh) {
			frappe.msgprint(__("Quantity cannot be greater than Quantity on Hand"));
			row.qty = row.qoh;
			frm.refresh_field('items');
		}
	},

	item_code: function(frm, cdt, cdn) {
		get_qoh(frm, cdt, cdn)
	},

	from_warehouse: function(frm, cdt, cdn) {
		// frm.events.get_item_data(frm, item, true);
		get_qoh(frm, cdt, cdn);
	},
});

var get_quantities_on_hand = function(frm) {
	if (frm.doc.items) {
		var rows = []
		$.each(frm.doc.items, function(i, d) {
			if (d.item_code && d.from_warehouse) {
				rows.push({"item": d.item_code, "warehouse": d.from_warehouse, "name": d.name});
			}
		});

		if (rows.length > 0) {
			get_qoh(frm, null, null, rows);
		}
	}
}

var get_qoh = function(frm, cdt=null, cdn=null, rows=null) {
	if (!rows){
		var row = locals[cdt][cdn];
		if (!row.item_code || !row.from_warehouse) {
			return
		}
		else{
			rows = [{
				"name": row.name,
				"item": row.item_code,
				"warehouse": row.from_warehouse
			}]
		}
	}


	frappe.call({
		method: "metactical.custom_scripts.material_request.material_request.get_qoh",
		args: {
			"filters": rows
		},
		callback: function(r) {
			var rows = r.message;

			$.each(rows, function(i, d) {
				var row = locals['Material Request Item'][d.name];
				row.qoh = d.qty;
			});

			frm.refresh_field('items');
		}
	});
}