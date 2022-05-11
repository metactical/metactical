// Copyright (c) 2021, Techlift Technologies and contributors
// For license information, please see license.txt

frappe.ui.form.on('Cycle Count', {
	onload: function(frm){
		frm.set_query('warehouse', function(){
			return {
				query: "metactical.metactical.doctype.cycle_count.cycle_count.get_permitted_warehouses",
				filters: {'user': frappe.session.user}
			};
		})
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
			frappe.call({
				method: "erpnext.selling.page.point_of_sale.point_of_sale.search_for_serial_or_batch_or_barcode_number",
				args: { search_value: frm.doc.scan_barcode }
			}).then(r => {
				const data = r && r.message;
				if (!data || Object.keys(data).length === 0) {
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
					row_to_modify = frappe.model.add_child(cur_frm.doc, cur_grid.doctype, 'items');
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

				scan_barcode_field.set_value('');
				refresh_field("items");
			});
		}
		return false;
	},
});

frappe.ui.form.on('Cycle Count Item', {
	item_code: function(frm, cdt, cdn){
		if(frm.doc.warehouse && locals[cdt][cdn].item_code){
			var item_code = locals[cdt][cdn].item_code;
			var warehouse = frm.doc.warehouse;
			frappe.call({
				method: "metactical.metactical.doctype.cycle_count.cycle_count.get_expected_qty",
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
});
