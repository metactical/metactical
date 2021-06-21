{% include 'erpnext/selling/sales_common.js' %}
var old_tax_template;
var base_in_words;
frappe.ui.form.on('Sales Order', {
		refresh: function(frm){
			console.log(frm);
		//Clear update qty and rate button
		/*if(frm.doc.docstatus === 1 && frm.doc.status !== 'Closed'
			&& flt(frm.doc.per_delivered, 6) < 100 && flt(frm.doc.per_billed, 6) < 100) {
			frm.clear_custom_buttons();
		}*/
		
		
		setTimeout(() => {
			
			frm.remove_custom_button("Pick List", 'Create'); 
			frm.add_custom_button(__('Pick List'), () => frm.events.create_pick_list_custom(), __("Create"));
			frm.remove_custom_button("Work Order", 'Create');
			frm.remove_custom_button("Request for Raw Materials", 'Create'); 
			frm.remove_custom_button("Project", 'Create'); 
			frm.remove_custom_button("Subscription", 'Create'); 
			
		}, 1000);

		// Add Stock Entry (Transfer material) button
		if(frm.doc.docstatus == 1){ 
			frm.add_custom_button(__('Stock Entry'), 
				() => frm.events.create_material_transfer_custom(), __("Create"));
		}
		
		//Code for custom cancel button that saves cancel reason first
		if(frm.doc.docstatus == 1){
			frm.page.clear_secondary_action();
			frm.page.set_secondary_action(__("Cancel"), function(frm) {
				cur_frm.events.before_cancel_event();
			});
		}

		// set taxes and charges after amending
		if (frm.doc.amended_from && !frm.doc.taxes_and_charges) {
			var amended_order = frappe.get_doc("Sales Order", frm.doc.amended_from);
			frm.doc.taxes_and_charges = amended_order.taxes_and_charges ;
		}

		dashboard_sales_order_doctype(frm, "Stock Entry");
		
	},

	onload: function(frm){
		old_tax_template = frm.doc.taxes_and_charges;
		base_in_words = frm.doc.base_in_words;
	},
	
	create_pick_list_custom(frm) {
		// confirm item availability
		var items = cur_frm.doc.items
		var flag = 0;
		var item_flag = ""
		items.forEach(function(row){
			if ((row.actual_qty - (row.qty + row.sal_reserved_qty)) < 0) {
				flag = 1;
				item_flag = row.item_code;
			}
		});
		if (flag != 1) {
			frappe.model.open_mapped_doc({
				method: "metactical.custom_scripts.pick_list.pick_list.create_pick_list",
				frm: cur_frm
			})
		}
		else{
			frappe.msgprint(__('Warning: Insufficient Stock for Item <a href="/desk#Form/Item/{0}">{0}</a> for this order',[item_flag]))
		}
	},

	create_material_transfer_custom() {
		frappe.model.open_mapped_doc({
			method: "metactical.custom_scripts.stock_entry.stock_entry.create_stock_entry",
			frm: cur_frm
		})
	},
	
	before_cancel_event: function(frm){
		frappe.prompt([
			{'fieldname': 'cancel_reason', 'fieldtype': 'Small Text', 'label': 'Enter Reason', 'reqd': 1}
		],
		function(values){
			frappe.call({
				'method': 'metactical.custom_scripts.sales_order.sales_order.save_cancel_reason',
				'args': {
					'docname': cur_frm.docname,
					'cancel_reason': values.cancel_reason
				},
				'callback': function(r){
					cur_frm.savecancel();
				}
			});
		},
		'Please reason for cancellation.',
		'Cancel'
		)
	},
	
});
frappe.ui.form.on("Sales Order Item", {
	item_code: function(frm,cdt,cdn) {
		var row = locals[cdt][cdn];
		if (row.item_code && row.warehouse) {
			return frm.call({
					method: "erpnext.stock.get_item_details.get_bin_details",
					child: row,
					args: {
						item_code: row.item_code,
						warehouse: row.warehouse,
					},
					callback:function(r){
						row.sal_reserved_qty =  r.message['reserved_qty']
						refresh_field("sal_reserved_qty", cdn, "items");
					}
				});
		}
	},
});

erpnext.selling.SalesOrderController = erpnext.selling.SalesOrderController.extend({
	customer_address: function(doc, dt, dn){
		if(doc.docstatus == 1){
			erpnext.utils.get_address_display(this.frm, "customer_address");		
		}
		else{
			erpnext.utils.get_address_display(this.frm, "customer_address");
			erpnext.utils.set_taxes_from_address(this.frm, "customer_address", "customer_address", "shipping_address_name");
		}
	},
	warehouse: function(doc, cdt, cdn){
		var row = locals[cdt][cdn];
		if (row.item_code && row.warehouse) {
			return this.frm.call({
					method: "erpnext.stock.get_item_details.get_bin_details",
					child: row,
					args: {
						item_code: row.item_code,
						warehouse: row.warehouse,
					},
					callback:function(r){
						row.sal_reserved_qty =  r.message['reserved_qty']
						refresh_field("sal_reserved_qty", cdn, "items");
					}
				});
		}
	},

});

$.extend(cur_frm.cscript, new erpnext.selling.SalesOrderController({frm: cur_frm}));


//Add Stock Entry in dashboard
var dashboard_sales_order_doctype = function (frm, doctype) {
		frappe.call({
				'method': 'metactical.custom_scripts.sales_order.sales_order.get_open_count',
				'args': {
					'docname': cur_frm.docname,
				},
				'callback': function(r){
					var items = [];
					$.each((r.message), function(i, d){
						items.push(d.name);		
					})
					load_template_links(frm, doctype, items);
				}
		});
}

var load_template_links = function(frm, doctype, items){
	var sales_orders = ['in'];
	var count_links = 0;
	items.forEach(function(item){
		console.log("in loop");		
		if( sales_orders.indexOf(item) == -1){
			count_links++;
			sales_orders.push(item);
		}
	});

	var parent = $('.form-dashboard-wrapper [data-doctype="Purchase Order"]').closest('div').parent();
	parent.find('[data-doctype="' + doctype + '"]').remove();
	parent.append(frappe.render_template("dashboard_sales_order_doctype", {
		doctype: doctype
	}));

	var self = parent.find('[data-doctype="' + doctype + '"]');
	

	// bind links
	self.find(".badge-link").on('click', function () {
		frappe.route_options = {
			"sales_order_no": frm.doc.name
		}
		frappe.set_route("List", doctype);
	});

	self.find('.count').html(count_links);
}

frappe.templates["dashboard_sales_order_doctype"] = ' \
    	<div class="document-link" data-doctype="{{ doctype }}"> \
    	<a class="badge-link small">{{ __(doctype) }}</a> \
    	<span class="text-muted small count"></span> \
    	<span class="open-notification hidden" title="{{ __("Open {0}", [__(doctype)])}}"></span> \
    	</div>';
