frappe.provide("erpnext");
frappe.provide("erpnext.utils");
erpnext.utils.update_child_items = function(opts) {
	const frm = opts.frm;
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
		columns: 3,
		label: __('Item Code')
	}, {
		fieldtype:'Float',
		fieldname:"qty",
		default: 0,
		read_only: 0,
		in_list_view: 1,
		columns: 1,
		label: __('Qty'),
		precision: get_precision("qty")
	}, {
		fieldtype:'Float',
		fieldname:"actual_qty",
		default: 0,
		read_only: 1,
		in_list_view: 1,
		label: __('Actual QOH')
	}, {
		fieldtype:'Currency',
		fieldname:"rate",
		default: 0,
		read_only: 0,
		in_list_view: 1,
		label: __('Rate'),
		precision: get_precision("rate")
	}];

	if (frm.doc.doctype == 'Sales Order' || frm.doc.doctype == 'Purchase Order' ) {
		fields.splice(2, 0, {
			fieldtype: 'Date',
			fieldname: frm.doc.doctype == 'Sales Order' ? "delivery_date" : "schedule_date",
			in_list_view: 0,
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
				in_place_edit: true,
				reqd: 1,
				data: this.data,
				get_data: () => {
					return this.data;
				},
				fields: fields
			},
		],
		primary_action: function() {
			const trans_items = this.get_values()["trans_items"];
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
		dialog.fields_dict.trans_items.df.data.push({
			"docname": d.name,
			"name": d.name,
			"item_code": d.item_code,
			"delivery_date": d.delivery_date,
			"schedule_date": d.schedule_date,
			"conversion_factor": d.conversion_factor,
			"qty": d.qty,
			"rate": d.rate,
			"actual_qty": d.actual_qty
		});
		this.data = dialog.fields_dict.trans_items.df.data;
		dialog.fields_dict.trans_items.grid.refresh();
	})
	dialog.show();
}
