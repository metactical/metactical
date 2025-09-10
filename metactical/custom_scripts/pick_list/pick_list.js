frappe.ui.form.on('Pick List', {
	refresh: function(frm){
		//Code for custom cancel button that saves cancel reason first
		if(frm.doc.docstatus == 1){
			frm.page.clear_secondary_action();
			frm.page.set_secondary_action(__("Cancel"), function(frm) {
				cur_frm.events.before_cancel_event();
			});
		}
		
		if(frm.doc.docstatus == 0 && frm.doc.__islocal == 1){
			frm.set_value('print_date_time', '');
			frm.set_value('track_print_user', '');
			frm.set_value('pl_text', '');
		}
		dashboard_pick_list_doctype(frm, "Sales Order");

	},

	before_save: async function(frm) {
		// validate if items table is not empty
		if (frm.doc.locations.length == 0) {
			frappe.throw(__("Please add items to the Pick List before saving."));
		}

		// validate if the reference sales order has a shipping address
		let sales_orders = frm.doc.locations.map(location => location.sales_order);

		if (sales_orders.length > 0) {
			// remove duplicates
			sales_orders = [...new Set(sales_orders)];

			for (const sales_order of sales_orders) {
				let r = await frappe.call({
					'method': 'frappe.client.get',
					'args': {
						'doctype': 'Sales Order',
						'name': sales_order
					}
				});

				if (!r.exc) {
					if (!r.message.shipping_address_name) {
						frappe.throw(__("Please make sure all referenced Sales Orders have a Shipping Address before saving the Pick List. Sales Order {0} does not have a Shipping Address.", [sales_order]));
					}
				}
			}
		}

		// Validating there is no duplicated items
		var item_list = [];
		var duplicated = false;
		var duplicated_item = [];
		for (const row of frm.doc.locations) {
			let result = await frappe.call({
				'method': 'metactical.custom_scripts.sales_order.sales_order.get_product_bundle_items',
				'args': { 'item_code': row.item_code }
			});

			if (result.message && result.message.length > 0) {
				let product_bundle_items = result.message;
				for (const pb_item of product_bundle_items) {
					if (item_list.includes(pb_item.item_code)) {
						duplicated = true;
						duplicated_item.push(pb_item.item_code);
					}
					item_list.push(pb_item.item_code);
				}
			}

			if (item_list.includes(row.item_code)) {
				duplicated = true;
				duplicated_item.push(row.item_code);
			}

			item_list.push(row.item_code);
		}

		if (duplicated) {
			duplicated_item = [...new Set(duplicated_item)];
			frappe.throw(__("Item(s) " + duplicated_item.join(", ") + " are duplicated. Please remove the duplicate before proceeding to create Pick List."));
		}
	},
	
	on_submit: function(frm){	
		setTimeout(function(){
			frm.reload_doc();

			if (frm.doc.docstatus == 1){
				var new_url = window.location.origin + "/printview?doctype=Pick%20List&name=" + frm.doc.name + "&trigger_print=1&format=PickList%204x6%20-%20V3&no_letterhead=0&_lang=en"		
				window.open(new_url)
			}
		}, 2000);
	},
	
	before_cancel_event: function(frm){
		frappe.prompt([
			{'fieldname': 'cancel_reason', 'fieldtype': 'Small Text', 'label': 'Enter Reason', 'reqd': 1}
		],
		function(values){
			frappe.call({
				'method': 'metactical.custom_scripts.pick_list.pick_list.save_cancel_reason',
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


//Add Sales Order in dashboard
var dashboard_pick_list_doctype = function (frm, doctype) {
	var sales_orders = ['in'];
	var count = 0;
	var locations = frm.doc.locations;
	
	locations.forEach(function(location){
		if(sales_orders.indexOf(location.sales_order) == -1){
			count++;
			sales_orders.push(location.sales_order);
		}
	});
	var parent = $('.form-dashboard-wrapper [data-doctype="Delivery Note"]').closest('div').parent();
	parent.find('[data-doctype="' + doctype + '"]').remove();
	parent.append(frappe.render_template("dashboard_pick_list_doctype", {
		doctype: doctype
	}));
	var self = parent.find('[data-doctype="' + doctype + '"]');
	
	//set_open_count(frm, doctype);
	// bind links
	self.find(".badge-link").on('click', function () {
		frappe.route_options = {
			"name": sales_orders
		}
		frappe.set_route("List", doctype);
	});
	
	self.find('.count').html(count);
}

frappe.templates["dashboard_pick_list_doctype"] = ' \
    	<div class="document-link" data-doctype="{{ doctype }}"> \
    	<a class="badge-link small">{{ __(doctype) }}</a> \
    	<span class="text-muted small count"></span> \
    	<span class="open-notification hidden" title="{{ __("Open {0}", [__(doctype)])}}"></span> \
    	</div>';

