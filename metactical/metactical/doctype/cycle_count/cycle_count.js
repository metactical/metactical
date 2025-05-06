// Copyright (c) 2021, Techlift Technologies and contributors
// For license information, please see license.txt

frappe.ui.form.on('Cycle Count', {
	refresh: function(frm) {
		if (frm.doc.docstatus == 0){
			if (!frm.doc.is_scanning) {
				frm.add_custom_button(__('Start Scanning'), function() {
					if (!frm.doc.warehouse) {
						frappe.msgprint({
							title: __('Warning'),
							indicator: 'orange',
							message: __('Please select a Warehouse')
						});
						return;
					}
					if (!frm.doc.items.length || (frm.doc.items.length == 1 && !frm.doc.items[0].item_code)) {
						frappe.throw(__('Please add items to the Cycle Count'));
						return;
					}
		
					frm.set_df_property("items", "read_only", 1);
					frm.set_df_property("scan_barcode", "read_only", 0);
					frm.set_value("is_scanning", 1);
					frm.save();
				})
			} else {
				frm.set_df_property("items", "read_only", 1);
				frm.set_df_property("scan_barcode", "read_only", 0);

				frm.add_custom_button(__('Stop Scanning'), function() {
					frm.set_df_property("items", "read_only", 0);
					frm.set_df_property("scan_barcode", "read_only", 1);
					frm.set_value("is_scanning", 0);
					frm.save();
				})
			}

			frm.add_custom_button(__('Template SKU'), function() {
				search_by_template_sku_dialog(frm);
			}, __('Get Items From'));
	
			frm.add_custom_button(__('Retail SKU'), function() {
				search_by_sku_dialog(frm);
			}, __('Get Items From'));
		}	
	},
	onload: function(frm) {
		frm.set_query('warehouse', function() {
			return {
				query: "metactical.metactical.doctype.cycle_count.cycle_count.get_permitted_warehouses",
				filters: {'user': frappe.session.user}
			};
		})
	},
	warehouse: function(frm) {
		if (frm.doc.warehouse) {
			frm.doc.items.forEach(child => {
				const cdt = child.doctype;
				const cdn = child.name;
				fetch_expected_qty(frm, cdt, cdn);
			});
		}
	},
	undo_last_scan: function(frm) {
		let last_scanned_item = frm.doc.last_scanned_item;
	
		if (!last_scanned_item) {
			frappe.show_alert({
				message: __("No item scanned yet"),
				indicator: 'orange'
			});
			frappe.utils.play_sound("error");
			return;
		}
	
		frm.doc.items = frm.doc.items.filter(item => {
			if (item.item_code === last_scanned_item) {
				item.qty -= 1;
				
				const cdt = item.doctype;
				const cdn = item.name;
				fetch_expected_qty(frm, cdt, cdn);
			}
			return true;
		});
	
		frm.set_value("last_scanned_item", null);
		refresh_field("items");
	},

	reset_table: function(frm) {
		frappe.confirm(__("Are you sure you want to reset the table?"), function() {
			console.log("Resetting table");

			if (frm.doc.template_sku) {
				get_items_from_template_sku(frm.doc.template_sku, frm);
			} else if (frm.doc.retail_sku) {
				get_items_from_retail_sku(frm.doc.retail_sku, frm);
			}
		});
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
					scan_barcode_field.set_value('');
					frappe.show_alert({
						message: __("Cannot find Item with this barcode"),
						indicator: 'orange'
					});
					scan_barcode_field.set_new_description(__('Cannot find Item with this barcode'));
					return;
				}

				const found = frm.doc.items.some(child => child.item_code === data.item_code);

				if (!found) {
					frappe.show_alert({
						message: __("Item not in this Cycle Count"),
						indicator: 'orange'
					});
					frappe.utils.play_sound("error");
					scan_barcode_field.set_value('');
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
					qty: (row_to_modify.qty || 0) + 1,
					difference: row_to_modify.qty - ((row_to_modify.expected_qty || 0) + 1),
				});

				frm.set_value("last_scanned_item", data.item_code);
				scan_barcode_field.set_value('');
				frm.refresh_field("items");
			});
		}
		return false;
	},
});

function fetch_expected_qty(frm, cdt, cdn) {
	const child = locals[cdt][cdn];
	if (frm.doc.warehouse && child.item_code) {
		const item_code = child.item_code;
		const warehouse = frm.doc.warehouse;

		frappe.call({
			method: "metactical.metactical.doctype.cycle_count.cycle_count.get_expected_qty",
			args: { item_code, warehouse },
			freeze: true,
			callback: function (ret) {
				if (ret.message !== undefined) {
					let qty = child.qty || 0;
					let expected_qty = ret.message.actual_qty;
					let difference = qty - expected_qty;

					frappe.model.set_value(cdt, cdn, "expected_qty", expected_qty);
					frappe.model.set_value(cdt, cdn, "valuation_rate", ret.message.valuation_rate);
					frappe.model.set_value(cdt, cdn, "difference", difference);
				}
			}
		});
	}
}

frappe.ui.form.on('Cycle Count Item', {
	item_code: function(frm, cdt, cdn){
		fetch_expected_qty(frm, cdt, cdn);
	},

	qty: function(frm, cdt, cdn){
		var child = locals[cdt][cdn];
		var difference = child.qty - child.expected_qty;
		frappe.model.set_value(cdt, cdn, "difference", difference);
		frm.refresh_field("items");
	}
});

function search_by_template_sku_dialog(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __('Get Item From Template SKU'),
		fields: [
			{
				fieldname: 'template_sku',
				fieldtype: 'Link',
				label: __('Temaplate SKU'),
				options: "Item",
				get_query: function () {
					return {
						filters: [["Item", "has_variants", "=", 1]],
					};
				},
				reqd: 1
			}
		],
		primary_action_label: __('Get Items'),
		primary_action(values) {
			dialog.hide();
			if (!values.template_sku) {
				frappe.msgprint({
					title: __('Warning'),
					indicator: 'orange',
					message: __('Please select a Template SKU')
				});
				return;
			}
			
			get_items_from_template_sku(values.template_sku, frm);
		}
	});

	dialog.show();
}

function search_by_sku_dialog(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __('Get Item From Retail SKU'),
		fields: [
			{
				fieldname: 'retail_sku',
				fieldtype: 'Data',
				label: __('Retail SKU'),
				reqd: 1
			}
		],
		primary_action_label: __('Get Items'),
		primary_action(values) {
			dialog.hide();
			if (!values.retail_sku) {
				frappe.msgprint({
					title: __('Warning'),
					indicator: 'orange',
					message: __('Please Enter a Retail SKU')
				});
				return;
			}
		
			get_items_from_retail_sku(values.retail_sku, frm);
		}
	});

	dialog.show();
}

function get_items_from_template_sku(template_sku, frm) {
	frappe.call({
		method: "metactical.metactical.doctype.cycle_count.cycle_count.get_items_from_template_sku",
		args: {
			template_sku: template_sku
		},
		freeze: true,
		callback: function (ret) {
			const items = ret.message;

			if (!items || !items.length) {
				frappe.show_alert({
					message: __("Cannot find Items with this Template SKU"),
					indicator: 'orange'
				});
				return;
			}

			update_items(frm, items);

			frm.set_value("template_sku", template_sku);
			frm.set_value("retail_sku", "");
		}
	});
}

function get_items_from_retail_sku(retail_sku, frm) {
	frappe.call({
		method: "metactical.metactical.doctype.cycle_count.cycle_count.get_items_from_retail_sku",
		args: {
			retail_sku: retail_sku
		},
		freeze: true,
		callback: function (ret) {
			const items = ret.message;

			if (!items || !items.length) {
				frappe.show_alert({
					message: __("Cannot find Items with this Retail SKU"),
					indicator: 'orange'
				});
				return;
			}

			update_items(frm, items);

			frm.set_value("retail_sku", retail_sku);
			frm.set_value("template_sku", "");
		}
	});
}

function update_items(frm, items) {
	frm.clear_table("items");

	items.forEach((item) => {
		const new_row = frm.add_child("items");
		new_row.item_code = item.name;
		new_row.retail_sku = item.ifw_retailskusuffix;
		new_row.ifw_location = item.ifw_location;
		new_row.qty = 0;
	});

	frm.refresh_field("items");

	frm.doc.items.forEach(child => {
		const cdt = child.doctype;
		const cdn = child.name;
		fetch_expected_qty(frm, cdt, cdn);
	});
}