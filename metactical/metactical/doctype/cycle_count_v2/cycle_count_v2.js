// Copyright (c) 2022, Techlift Technologies and contributors
// For license information, please see license.txt

frappe.ui.form.on('Cycle Count V2', {
	onload: function(frm){
		frm.set_query('warehouse', function(){
			return {
				query: "metactical.metactical.doctype.cycle_count_v2.cycle_count_v2.get_permitted_warehouses",
				filters: {'user': frappe.session.user}
			};
		})
		console.log(frm);
	},
	
	onload_post_render: function(frm){
		/*frm.fields_dict.scan_barcode.$wrapper.on('keypress', function(event){
			if(event.keyCode == 13)
			{
				$("[data-fieldname=scan_barcode]").focus()
				cur_frm.events.scanned_barcode(cur_frm);
			}
		});
		
		frm.$wrapper.on('keypress', function(event){
			if(event.keyCode == 13)
			{
				return false;
			}
		});
		
		frm.fields_dict.get_items.$wrapper.on('click', function(event){
			frm.events.get_items_event(cur_frm);
		});*/
	},
	
	get_items: function(frm){
		if(!frm.doc.items){
			frappe.call({
				method: "metactical.metactical.doctype.cycle_count_v2.cycle_count_v2.get_items",
				args: {
					'warehouse': frm.doc.warehouse,
					'ifw_location': frm.doc.ifw_location.replace(/\s/g,'')
				},
				freeze: true,
				callback: function(ret){
					if(typeof ret.message != undefined){
						frm.doc.items = [];
						for(let row in ret.message){
							var child = cur_frm.add_child("items");
							child.item_code = ret.message[row].item_code;
							child.expected_qty = ret.message[row].actual_qty;
							child.valuation_rate = ret.message[row].valuation_rate;
						}
						cur_frm.refresh_fields('items');
					}
				}
			});
		}
	},
	
	scan_barcode: function(frm) {
		let scan_barcode_field = frm.fields_dict["scan_barcode"];

		let show_description = function(idx, exist = null) {
			if (exist) {
				scan_barcode_field.set_new_description(__('Row #{0}: Qty increased by 1', [idx]));
			} else {
				scan_barcode_field.set_new_description(__('Row #{0}: Item added', [idx]));
			}
		}

		if(frm.doc.scan_barcode) {
			scan_barcode_field.set_new_description(__(''));
			frappe.call({
				method: "erpnext.selling.page.point_of_sale.point_of_sale.search_for_serial_or_batch_or_barcode_number",
				args: { search_value: frm.doc.scan_barcode }
			}).then(r => {
				const data = r && r.message;
				if (!data || Object.keys(data).length === 0) {
					frappe.utils.play_sound("error");
					scan_barcode_field.set_value('');
					frappe.show_alert({
						message: __("Cannot find Item with this barcode"),
						indicator: 'orange'
					});
					scan_barcode_field.set_new_description(__('Cannot find Item with this barcode'));
					return;
				}

				let cur_grid = cur_frm.fields_dict.items.grid;

				let row_to_modify = null;
				const existing_item_row = cur_frm.doc.items.find(d => d.item_code === data.item_code);
				const blank_item_row = cur_frm.doc.items.find(d => !d.item_code);

				if (existing_item_row) {
					row_to_modify = existing_item_row;
				} else if (blank_item_row) {
					row_to_modify = blank_item_row;
				}

				if (!row_to_modify) {
					// add new row
					//row_to_modify = frappe.model.add_child(cur_frm.doc, cur_grid.doctype, 'items');
					frappe.throw('Error: Item not in location')
				}

				//show_description(row_to_modify.idx, row_to_modify.item_code);

				cur_frm.from_barcode = true;
				frappe.model.set_value(row_to_modify.doctype, row_to_modify.name, {
					item_code: data.item_code,
					qty: (row_to_modify.qty || 0) + 1
				});

				/*['serial_no', 'batch_no', 'barcode'].forEach(field => {
					if (data[field] && frappe.meta.has_field(row_to_modify.doctype, field)) {

						let value = (row_to_modify[field] && field === "serial_no")
							? row_to_modify[field] + '\n' + data[field] : data[field];

						frappe.model.set_value(row_to_modify.doctype,
							row_to_modify.name, field, value);
					}
				});*/

				frappe.utils.play_sound("alert");
				scan_barcode_field.set_value('');
				refresh_field("items");
			});
		}
		return false;
	},
});

/*frappe.ui.form.on('Cycle Count V2 Item', {
	item_code: function(frm, cdt, cdn){
		if(frm.doc.warehouse && locals[cdt][cdn].item_code){
			var item_code = locals[cdt][cdn].item_code;
			var warehouse = frm.doc.warehouse;
			frappe.call({
				method: "metactical.metactical.doctype.cycle_count_v2.cycle_count_v2.get_expected_qty",
				args: {"item_code": item_code, "warehouse": warehouse},
				freeze: true,
				callback: function(ret){
					console.log(ret);
					if(typeof ret.message != undefined){
						frappe.model.set_value(cdt, cdn, "expected_qty", ret.message.actual_qty);
						frappe.model.set_value(cdt, cdn, "valuation_rate", ret.message.valuation_rate);
					}
				}
			});
		}
	}
});*/

