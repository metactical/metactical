frappe.ui.form.on('Purchase Order', {
	refresh: function(frm){
		frm.doc.taxes.forEach((row)=>{
			var allow_tax_edit = 1;
			var tax_fields = ['charge_type', 'account_head', 'rate']
			if(frm.doc.__onload['ais_allow_tax_edit']){
				allow_tax_edit = 0;
			}
			frm.set_df_property('taxes', 'read_only', allow_tax_edit);
			tax_fields.forEach((field) => {
				frappe.meta.get_docfield(row.doctype, field, row.name).read_only = allow_tax_edit;
			});
			frm.refresh_field("taxes");
		});
	}
});

erpnext.buying.CustomPurchaseOrderController = erpnext.buying.PurchaseOrderController.extend({
	onload: function(doc, cdt, cdn){
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
		
		//Remove address if it's new doc
		if(this.frm.doc.__islocal == 1){
			setTimeout(() => {
				this.frm.set_value("shipping_address", '');
				this.frm.set_value("billing_address", "");
			}, 1000)
		}
	},
	
	supplier: function(doc, cdt, cdn){
		//Remove address
		this.frm.set_value("shipping_address", '');
	},
	
	add_from_mappers: function() {
		var me = this;
		this.frm.add_custom_button(__('Material Request'),
			function() {
				erpnext.utils.map_current_doc({
					method: "erpnext.stock.doctype.material_request.material_request.make_purchase_order",
					source_doctype: "Material Request",
					target: me.frm,
					setters: [
						{
							"fieldtype": "Data",
							"fieldname": "ais_suppliers",
							"label": __("Supplier"),
							"default": ''
						}
					],
					get_query_filters: {
						material_request_type: "Purchase",
						docstatus: 1,
						status: ["!=", "Stopped"],
						per_ordered: ["<", 99.99],
					}
				})
			}, __("Get items from"));

		this.frm.add_custom_button(__('Supplier Quotation'),
			function() {
				erpnext.utils.map_current_doc({
					method: "erpnext.buying.doctype.supplier_quotation.supplier_quotation.make_purchase_order",
					source_doctype: "Supplier Quotation",
					target: me.frm,
					setters: {
						company: me.frm.doc.company
					},
					get_query_filters: {
						docstatus: 1,
						status: ["!=", "Stopped"],
					}
				})
			}, __("Get items from"));

		this.frm.add_custom_button(__('Update rate as per last purchase'),
			function() {
				frappe.call({
					"method": "get_last_purchase_rate",
					"doc": me.frm.doc,
					callback: function(r, rt) {
						me.frm.dirty();
						me.frm.cscript.calculate_taxes_and_totals();
					}
				})
			}, __("Tools"));

		this.frm.add_custom_button(__('Link to Material Request'),
		function() {
			var my_items = [];
			for (var i in me.frm.doc.items) {
				if(!me.frm.doc.items[i].material_request){
					my_items.push(me.frm.doc.items[i].item_code);
				}
			}
			frappe.call({
				method: "erpnext.buying.utils.get_linked_material_requests",
				args:{
					items: my_items
				},
				callback: function(r) {
					if(r.exc) return;

					var i = 0;
					var item_length = me.frm.doc.items.length;
					while (i < item_length) {
						var qty = me.frm.doc.items[i].qty;
						(r.message[0] || []).forEach(function(d) {
							if (d.qty > 0 && qty > 0 && me.frm.doc.items[i].item_code == d.item_code && !me.frm.doc.items[i].material_request_item)
							{
								me.frm.doc.items[i].material_request = d.mr_name;
								me.frm.doc.items[i].material_request_item = d.mr_item;
								var my_qty = Math.min(qty, d.qty);
								qty = qty - my_qty;
								d.qty = d.qty  - my_qty;
								me.frm.doc.items[i].stock_qty = my_qty * me.frm.doc.items[i].conversion_factor;
								me.frm.doc.items[i].qty = my_qty;

								frappe.msgprint("Assigning " + d.mr_name + " to " + d.item_code + " (row " + me.frm.doc.items[i].idx + ")");
								if (qty > 0) {
									frappe.msgprint("Splitting " + qty + " units of " + d.item_code);
									var new_row = frappe.model.add_child(me.frm.doc, me.frm.doc.items[i].doctype, "items");
									item_length++;

									for (var key in me.frm.doc.items[i]) {
										new_row[key] = me.frm.doc.items[i][key];
									}

									new_row.idx = item_length;
									new_row["stock_qty"] = new_row.conversion_factor * qty;
									new_row["qty"] = qty;
									new_row["material_request"] = "";
									new_row["material_request_item"] = "";
								}
							}
						});
						i++;
					}
					refresh_field("items");
				}
			});
		}, __("Tools"));
	},
	
	get_items_from_open_material_requests: function() {
		this.map_current_doc({
			method: "metactical.custom_scripts.purchase_order.purchase_order.make_purchase_order_based_on_supplier",
			source_name: this.frm.doc.supplier,
			get_query_filters: {
				docstatus: ["!=", 2],
			}
		});
	},
	
	map_current_doc: function(opts) {
		var me = this;
		frappe.dom.freeze();
		if(opts.get_query_filters) {
			opts.get_query = function() {
				return {filters: opts.get_query_filters};
			}
		}
		var _map = function() {
			if($.isArray(cur_frm.doc.items) && cur_frm.doc.items.length > 0) {
				// remove first item row if empty
				if(!cur_frm.doc.items[0].item_code) {
					cur_frm.doc.items = cur_frm.doc.items.splice(1);
				}

				// find the doctype of the items table
				var items_doctype = frappe.meta.get_docfield(cur_frm.doctype, 'items').options;

				// find the link fieldname from items table for the given
				// source_doctype
				var link_fieldname = null;
				frappe.get_meta(items_doctype).fields.forEach(function(d) {
					if(d.options===opts.source_doctype) link_fieldname = d.fieldname; });

				// search in existing items if the source_name is already set and full qty fetched
				var already_set = false;
				var item_qty_map = {};

				$.each(cur_frm.doc.items, function(i, d) {
					opts.source_name.forEach(function(src) {
						if(d[link_fieldname]==src) {
							already_set = true;
							if (item_qty_map[d.item_code])
								item_qty_map[d.item_code] += flt(d.qty);
							else
								item_qty_map[d.item_code] = flt(d.qty);
						}
					});
				});

				if(already_set) {
					opts.source_name.forEach(function(src) {
						frappe.model.with_doc(opts.source_doctype, src, function(r) {
							var source_doc = frappe.model.get_doc(opts.source_doctype, src);
							$.each(source_doc.items || [], function(i, row) {
								if(row.qty > flt(item_qty_map[row.item_code])) {
									already_set = false;
									return false;
								}
							})
						})

						if(already_set) {
							frappe.msgprint(__("You have already selected items from {0} {1}",
								[opts.source_doctype, src]));
							return;
						}

					})
				}
			}
			return frappe.call({
				// Sometimes we hit the limit for URL length of a GET request
				// as we send the full target_doc. Hence this is a POST request.
				type: "POST",
				method: 'frappe.model.mapper.map_docs',
				args: {
					"method": opts.method,
					"source_names": opts.source_name,
					"target_doc": cur_frm.doc,
					'args': opts.args
				},
				callback: function(r) {
					if(!r.exc) {
						var doc = frappe.model.sync(r.message);
						frappe.run_serially([
							() => cur_frm.dirty(),
							() => me.apply_price_list(),
							() => cur_frm.refresh(),
							() => frappe.dom.unfreeze()
						]);
					}
				}
			});
		}
		if(opts.source_doctype) {
			var d = new frappe.ui.form.MultiSelectDialog({
				doctype: opts.source_doctype,
				target: opts.target,
				date_field: opts.date_field || undefined,
				setters: opts.setters,
				get_query: opts.get_query,
				action: function(selections, args) {
					let values = selections;
					if(values.length === 0){
						frappe.msgprint(__("Please select {0}", [opts.source_doctype]))
						return;
					}
					opts.source_name = values;
					opts.setters = args;
					d.dialog.hide();
					_map();
				},
			});
		} else if(opts.source_name) {
			opts.source_name = [opts.source_name];
			_map();
		}
	}
})
// for backward compatibility: combine new and previous states
$.extend(cur_frm.cscript, new erpnext.buying.CustomPurchaseOrderController({frm: cur_frm}));
