frappe.provide("erpnext");
frappe.provide("erpnext.utils");
erpnext.utils.update_child_items = function(opts) {
	const frm = opts.frm;
	/*for(let row in frm.doc.items){
		if(frm.doc.items[row].picked_qty > 0){
			frappe.throw('A pick list has already been created for this Order. Please cancel it first.');
		}
	}*/
	const cannot_add_row = (typeof opts.cannot_add_row === 'undefined') ? true : opts.cannot_add_row;
	const child_docname = (typeof opts.cannot_add_row === 'undefined') ? "items" : opts.child_docname;
	const child_meta = frappe.get_meta(`${frm.doc.doctype} Item`);
	const get_precision = (fieldname) => child_meta.fields.find(f => f.fieldname == fieldname).precision;

	this.data = [];
	const fields = [{
		fieldtype:'Data',
		fieldname:"docname",
		read_only: 1,
		hidden: 1,
	}, {
		fieldtype:'Link',
		fieldname:"item_code",
		options: 'Item',
		in_list_view: 1,
		read_only: 0,
		disabled: 0,
		label: __('Item Code'),
		get_query: function() {
			let filters;
			if (frm.doc.doctype == 'Sales Order') {
				filters = {"is_sales_item": 1};
			} else if (frm.doc.doctype == 'Purchase Order') {
				if (frm.doc.is_subcontracted == "Yes") {
					filters = {"is_sub_contracted_item": 1};
				} else {
					filters = {"is_purchase_item": 1};
				}
			}
			return {
				query: "erpnext.controllers.queries.item_query",
				filters: filters
			};
		}
	}, {
		fieldtype:'Link',
		fieldname:'uom',
		options: 'UOM',
		read_only: 0,
		label: __('UOM'),
		reqd: 1,
		onchange: function () {
			frappe.call({
				method: "erpnext.stock.get_item_details.get_conversion_factor",
				args: { item_code: this.doc.item_code, uom: this.value },
				callback: r => {
					if(!r.exc) {
						if (this.doc.conversion_factor == r.message.conversion_factor) return;

						const docname = this.doc.docname;
						dialog.fields_dict.trans_items.df.data.some(doc => {
							if (doc.docname == docname) {
								doc.conversion_factor = r.message.conversion_factor;
								dialog.fields_dict.trans_items.grid.refresh();
								return true;
							}
						})
					}
				}
			});
		}
	}, {
		fieldtype:'Float',
		fieldname:"qty",
		default: 0,
		read_only: 0,
		in_list_view: 1,
		label: __('Qty'),
		precision: get_precision("qty")
	}, {
		fieldtype:'Currency',
		fieldname:"rate",
		options: "currency",
		default: 0,
		read_only: 0,
		in_list_view: 1,
		label: __('Rate'),
		precision: get_precision("rate")
	}, {
		fieldtype: 'Float',
		fieldname: 'picked_qty',
		default: 0,
		read_only: 1,
		in_list_view: 0,
		label: __('Picked Qty'),
		precision: get_precision('picked_qty')
	}];

	if (frm.doc.doctype == 'Sales Order' || frm.doc.doctype == 'Purchase Order' ) {
		fields.splice(2, 0, {
			fieldtype: 'Date',
			fieldname: frm.doc.doctype == 'Sales Order' ? "delivery_date" : "schedule_date",
			in_list_view: 1,
			label: frm.doc.doctype == 'Sales Order' ? __("Delivery Date") : __("Reqd by date"),
			reqd: 1
		})
		fields.splice(3, 0, {
			fieldtype: 'Float',
			fieldname: "conversion_factor",
			in_list_view: 1,
			label: __("Conversion Factor"),
			precision: get_precision('conversion_factor')
		})
	}

	const dialog = new frappe.ui.Dialog({
		title: __("Update Items"),
		fields: [
			{
				fieldname: "trans_items",
				fieldtype: "Table",
				label: "Items",
				cannot_add_rows: cannot_add_row,
				in_place_edit: false,
				reqd: 1,
				data: this.data,
				get_data: () => {
					return this.data;
				},
				fields: fields
			},
		],
		primary_action: function() {
			//Add already picked items in Sales orders
			if(frm.doc.doctype == 'Sales Order'){
				frm.doc[opts.child_docname].forEach(d => {
					if(d.picked_qty == d.qty){
						this.fields_dict.trans_items.df.data.push({
							"docname": d.name,
							"name": d.name,
							"item_code": d.item_code,
							"delivery_date": d.delivery_date,
							"schedule_date": d.schedule_date,
							"conversion_factor": d.conversion_factor,
							"qty": d.qty,
							"rate": d.rate,
							"uom": d.uom,
							"picked_qty": d.picked_qty
						});
						this.data = dialog.fields_dict.trans_items.df.data;
					}
				});
			}
			const trans_items = this.get_values()["trans_items"].filter((item) => !!item.item_code);
			//Validate picked_qty < qty
			if(frm.doc.doctype == 'Sales Order'){
				trans_items.forEach(row => {
					if(row.picked_qty > row.qty){
						frappe.throw("Quantity can not be greater than the already picked qty for item " + row.item_code);
					}
				});
			}
			
			frappe.call({
				method: 'erpnext.controllers.accounts_controller.update_child_qty_rate',
				freeze: true,
				args: {
					'parent_doctype': frm.doc.doctype,
					'trans_items': trans_items,
					'parent_doctype_name': frm.doc.name,
					'child_docname': child_docname
				},
				callback: function() {
					frm.reload_doc();
				}
			});
			this.hide();
			refresh_field("items");
		},
		primary_action_label: __('Update')
	});

	frm.doc[opts.child_docname].forEach(d => {
		if(frm.doc.doctype == 'Sales Order' && d.picked_qty < d.qty){
			dialog.fields_dict.trans_items.df.data.push({
				"docname": d.name,
				"name": d.name,
				"item_code": d.item_code,
				"delivery_date": d.delivery_date,
				"schedule_date": d.schedule_date,
				"conversion_factor": d.conversion_factor,
				"qty": d.qty,
				"rate": d.rate,
				"uom": d.uom,
				"picked_qty": d.picked_qty
			});
			this.data = dialog.fields_dict.trans_items.df.data;
			dialog.fields_dict.trans_items.grid.refresh();
		}
		else if(frm.doc.doctype != 'Sales Order'){
			dialog.fields_dict.trans_items.df.data.push({
				"docname": d.name,
				"name": d.name,
				"item_code": d.item_code,
				"delivery_date": d.delivery_date,
				"schedule_date": d.schedule_date,
				"conversion_factor": d.conversion_factor,
				"qty": d.qty,
				"rate": d.rate,
				"uom": d.uom,
				"picked_qty": d.picked_qty
			});
			this.data = dialog.fields_dict.trans_items.df.data;
			dialog.fields_dict.trans_items.grid.refresh();
		}
	})
	dialog.show();
}
