frappe.ui.form.on('Purchase Order', {
	refresh: function(frm){
		var allow_tax_edit = 1;
		if(frm.doc.__onload['ais_allow_tax_edit']){
			allow_tax_edit = 0;
		}
		frm.set_df_property('taxes', 'read_only', allow_tax_edit);
		frm.doc.taxes.forEach((row)=>{
			var tax_fields = ['charge_type', 'account_head', 'rate']
			tax_fields.forEach((field) => {
				frappe.meta.get_docfield(row.doctype, field, row.name).read_only = allow_tax_edit;
			});
			frm.refresh_field("taxes");
		});
	}
});

erpnext.buying.CustomPurchaseOrderController = erpnext.buying.PurchaseOrderController.extend({
	onload: function(doc, cdt, cdn){
		this.setup_queries(doc, cdt, cdn);
		this._super();

		this.frm.set_query('shipping_rule', function() {
			return {
				filters: {
					"shipping_rule_type": "Buying"
				}
			};
		});

		if (this.frm.doc.__islocal
			&& frappe.meta.has_field(this.frm.doc.doctype, "disable_rounded_total")) {

				var df = frappe.meta.get_docfield(this.frm.doc.doctype, "disable_rounded_total");
				var disable = cint(df.default) || cint(frappe.sys_defaults.disable_rounded_total);
				this.frm.set_value("disable_rounded_total", disable);
		}

		/* eslint-disable */
		// no idea where me is coming from
		
		// Metactical Customization: Made company address available in shipping address 
		// filter in PO even when drop ship PO
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
		/* eslint-enable */
		// Metactical Customization: Remove address if it's new doc
		if(this.frm.doc.__islocal == 1){
			setTimeout(() => {
				this.frm.set_value("shipping_address", '');
				this.frm.set_value("billing_address", "");
			}, 1000)
		}
	},
	
	supplier: function(doc, cdt, cdn){
		var me = this;
		erpnext.utils.get_party_details(this.frm, null, null, function(){
			me.apply_price_list();
		});
		// Metactical Customization: Remove address
		this.frm.set_value("shipping_address", '');
	},
	
	add_from_mappers: function() {
		var me = this;
		this.frm.add_custom_button(__('Material Request'),
			// Metactical Customization: Add supplier filter
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
						per_ordered: ["<", 100],
						company: me.frm.doc.company
					},
					allow_child_item_selection: true,
					child_fieldname: "items",
					child_columns: ["item_code", "qty"]
				})
			}, __("Get Items From"));

		this.frm.add_custom_button(__('Supplier Quotation'),
			function() {
				erpnext.utils.map_current_doc({
					method: "erpnext.buying.doctype.supplier_quotation.supplier_quotation.make_purchase_order",
					source_doctype: "Supplier Quotation",
					target: me.frm,
					setters: {
						supplier: me.frm.doc.supplier,
						valid_till: undefined
					},
					get_query_filters: {
						docstatus: 1,
						status: ["not in", ["Stopped", "Expired"]],
					}
				})
			}, __("Get Items From"));

		this.frm.add_custom_button(__('Update Rate as per Last Purchase'),
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
			args: {
				supplier: this.frm.doc.supplier
			},
			source_doctype: "Material Request",
			source_name: this.frm.doc.supplier,
			target: this.frm,
			setters: {
				company: me.frm.doc.company
			},
			get_query_filters: {
				docstatus: ["!=", 2],
				supplier: this.frm.doc.supplier
			},
			get_query_method: "erpnext.stock.doctype.material_request.material_request.get_material_requests_based_on_supplier"
		});
	},
	
	map_current_doc: function(opts) {
		// Metactical Customization: Moved the location for price list information
		// load. Not sure why
		var me = this;
		frappe.dom.freeze();
		
		function _map() {
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
				
				// Metactical Customization: Moved the location for price list information
				// load. Not sure why
				type: "POST",
				method: 'frappe.model.mapper.map_docs',
				args: {
					"method": opts.method,
					"source_names": opts.source_name,
					"target_doc": cur_frm.doc,
					"args": opts.args
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
		
		let query_args = {};
		if (opts.get_query_filters) {
			query_args.filters = opts.get_query_filters;
		}

		if (opts.get_query_method) {
			query_args.query = opts.get_query_method;
		}

		if (query_args.filters || query_args.query) {
			opts.get_query = () => query_args;
		}

		if (opts.source_doctype) {
			const d = new frappe.ui.form.MultiSelectDialog({
				doctype: opts.source_doctype,
				target: opts.target,
				date_field: opts.date_field || undefined,
				setters: opts.setters,
				get_query: opts.get_query,
				add_filters_group: 1,
				allow_child_item_selection: opts.allow_child_item_selection,
				child_fieldname: opts.child_fieldname,
				child_columns: opts.child_columns,
				size: opts.size,
				action: function(selections, args) {
					let values = selections;
					if (values.length === 0) {
						frappe.msgprint(__("Please select {0}", [opts.source_doctype]))
						return;
					}
					opts.source_name = values;
					if (opts.allow_child_item_selection) {
						// args contains filtered child docnames
						opts.args = args;
					}
					d.dialog.hide();
					_map();
				},
			});

			return d;
		}

		if (opts.source_name) {
			opts.source_name = [opts.source_name];
			_map();
		}
	}
})
// for backward compatibility: combine new and previous states
$.extend(cur_frm.cscript, new erpnext.buying.CustomPurchaseOrderController({frm: cur_frm}));
