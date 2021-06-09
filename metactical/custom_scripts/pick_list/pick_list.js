frappe.ui.form.on('Pick List', {
	refresh: function(frm){
		console.log(frm);
		
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
		get_undelivered_pick_list(frm);

	},
	
	on_submit: function(frm){				
		var new_url = window.location.origin + "/printview?doctype=Pick%20List&name=" + frm.doc.name + "&trigger_print=1&format=Pick%20List%204*6&no_letterhead=0&_lang=en"		
		window.open(new_url)
		
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

var get_undelivered_pick_list = function (frm) {
	
	var count = 0;
	var locations = frm.doc.locations;
	
	locations.forEach(function(row){
		frappe.call({
			'method': 'metactical.custom_scripts.pick_list.pick_list.get_undelivered_pick_list',
			'args': {
				'item_code': row.item_code,
				'warehouse': row.warehouse,
			},
			'callback': function(r){
				var items = [];
				$.each((r.message), function(i, d){
					items.push(d);		
				})
				set_qoh_flag(frm, items);
			}
		});
	});

}

// set qoh
var set_qoh_flag = function(frm, items){
	
	var undelivered_pick_list = [];
	/*var flag = 0;
	var flagged_item = '';*/
	items.forEach(function(row){
		console.log(row);	
		if ((row.actual_qty - row.reserved_qty) < 0){
			frm.doc.flag_qty = 1;
			frm.doc.flagged_item = row.item_code;
		}	
	
	});
	var btn = document.getElementsByClassName('btn-print-print');
    if(btn) {
        for(var i = 0; i < btn.length; i++) {
            if (btn[i].textContent.trim() == "Print") {
                btn[i].addEventListener("click", function () {
                	if (frm.doc.flag_qty==1) {
                		console.log("yesss");
                		frappe.validated = false;
                		frappe.msgprint(__("Insufficient Qty for Item: "+ frm.doc.flagged_item))
                	}
                    console.log("flag:" +frm.doc.flag_qty);
                    //frappe.throw(("Not allowed to print as Qty is Insufficient"))
                    //frappe.msgprint(__("Insufficient Qty for Item: "+ frm.doc.flagged_item))
                });
                break;
            }
        }
    }
}

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

