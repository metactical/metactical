{% include 'erpnext/selling/sales_common.js' %}
var old_tax_template;
var base_in_words;
frappe.ui.form.on('Sales Order', {
	refresh: function(frm){
		if (frm.doc.__islocal)
			frm.set_value("neb_payment_completed_at", null)
		
		//Clear update qty and rate button
		/*if(frm.doc.docstatus === 1 && frm.doc.status !== 'Closed'
			&& flt(frm.doc.per_delivered, 6) < 100 && flt(frm.doc.per_billed, 6) < 100) {
			frm.clear_custom_buttons();
		}*/
		
		
		setTimeout(() => {
			
			frm.remove_custom_button("Pick List", 'Create'); 
			frm.add_custom_button(__('Pick List'), () => frm.events.create_pick_list_custom(frm), __("Create"));
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
		
		//For changing to drop ship
		if(frm.doc.docstatus == 1 && (frm.doc.delivery_status == "Not Delivered" || frm.doc.delivery_status == "Partly Delivered")){
			frm.add_custom_button(__('To Drop Ship'), () => frm.events.change_to_drop_ship(frm), __('Change'));
			frm.add_custom_button(__('Warehouse'), () => frm.events.change_warehouse(frm), __('Change'));
		}
		
		cur_frm.fields_dict["section_break_48"].collapse(0);
	},

	onload: function(frm){
		old_tax_template = frm.doc.taxes_and_charges;
		base_in_words = frm.doc.base_in_words;
		if(!frm.doc.delivery_date){
			let delivery_date = new Date();
			frm.set_value("delivery_date", delivery_date.toISOString().split('T')[0]);
		}
	},
	
	change_to_drop_ship: function(frm){
		var fields = [
			{
				"fieldtype": "Data",
				"fieldname": "docname",
				"read_only": 1,
				"hidden": 1,
				"in_list_view": 0
			},
			{
				"fieldtype": "Link",
				"options": "Item",
				"fieldname": "item_code",
				"read_only": 1,
				"columns": 2,
				"label": __("Item Code"),
				"in_list_view": 1
			},
			{
				"fieldtype": "Data",
				"fieldname": "item_name",
				"read_only": 1,
				"columns": 3,
				"label": __("Item Name"),
				"in_list_view": 1
			},
			{
				"fieldtype": "Check",
				"fieldname": "delivered_by_supplier",
				"read_only": 0,
				"columns": 1,
				"label": __("Delivered By Supplier"),
				"in_list_view": 1
			},
			{
				"fieldtype": "Link",
				"options": "Supplier",
				"fieldname": "supplier",
				"read_only": 0,
				"columns": 3,
				"label": __("Supplier"),
				"in_list_view": 1
			}
		];
		var data = [];
		frm.doc.items.forEach(function(row){
			if(row.delivered_by_supplier != 1 && row.delivered_qty == 0){
				data.push({
					"docname": row.name,
					"item_code": row.item_code,
					"item_name": row.item_name
				})
			}
		});
		var dialog = new frappe.ui.Dialog({
			title: __("Update Drop Ship"),
			fields: [
				{
					fieldname: "drop_ship_items",
					fieldtype: "Table",
					label: "Items",
					cannot_add_rows: true,
					in_place_edit: true,
					reqd: 1,
					data: data,
					get_data: () => {
						return data;
					},
					fields: fields
				}
			],
			primary_action: function() {
				const drop_ship_items = this.get_values()["drop_ship_items"];
				frappe.call({
					method: 'metactical.custom_scripts.sales_order.sales_order.update_drop_shipping',
					freeze: true,
					args: {
						'items': drop_ship_items
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
		
		
		
		dialog.show();
	},
	
	create_pick_list_custom: function(frm) {
		// confirm item availability
		var items = cur_frm.doc.items
		var flag = 0;
		var item_flag = [];
		var proceed = true;
		items.forEach(function(row){

			if (row.ais_is_stock_item == 1 && (row.actual_qty - (row.qty + row.sal_reserved_qty)) < 0) {
				flag = 1;
				item_flag.push(row.item_code);
				proceed = false;
			}
		});


		if (flag == 1) {
			item_flag = item_flag.join(', ');
			frappe.confirm(
				'Warning: Insufficient stock for Item ' + item_flag + '. Do you want to proceed anyway?',
				function(){
					frm.events.open_pick_list(frm);
				},
				function(){
					proceed = false;
				}
			)
		}
		
		if(frm.doc.ifw_signifyd_guaranteedisposition != 'APPROVED'){
			proceed = false;
			frappe.confirm(
				'Warning: The order has not been approved by SignifyD. Do you want to proceed anyway?',
				function(){
					if(flag != 1){ //Check that there is sufficient stock first
						frm.events.open_pick_list(frm);
					}
				},
				function(){
					proceed = false;
				}
			);
		}
		
		if(proceed){
			frm.events.open_pick_list(frm);
		}
	},
	
	open_pick_list: function(frm) {
		frappe.model.open_mapped_doc({
			method: "metactical.custom_scripts.pick_list.pick_list.create_pick_list",
			frm: cur_frm
		});
	},

	create_material_transfer_custom: function() {
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
	
	change_warehouse: function(frm){
		var fields = [
			{
				"fieldtype": "Data",
				"fieldname": "docname",
				"read_only": 1,
				"hidden": 1,
				"in_list_view": 0
			},
			{
				"fieldtype": "Link",
				"options": "Item",
				"fieldname": "item_code",
				"read_only": 1,
				"columns": 2,
				"label": __("Item Code"),
				"in_list_view": 1
			},
			{
				"fieldtype": "Data",
				"fieldname": "item_name",
				"read_only": 1,
				"columns": 2,
				"label": __("Item Name"),
				"in_list_view": 1
			},
			{
				"fieldtype": "Link",
				"options": "Warehouse",
				"fieldname": "warehouse",
				"read_only": 0,
				"columns": 3,
				"label": __("Warehouse"),
				"in_list_view": 1
			}
		];
		var data = [];
		frm.doc.items.forEach(function(row){
			data.push({
				"docname": row.name,
				"item_code": row.item_code,
				"item_name": row.item_name,
				"warehouse": row.warehouse
			});
		});
		var dialog = new frappe.ui.Dialog({
			title: __("Change Warehouse"),
			fields: [
				{
					fieldname: "items",
					fieldtype: "Table",
					label: "Items",
					cannot_add_rows: true,
					in_place_edit: true,
					reqd: 1,
					data: data,
					get_data: () => {
						return data;
					},
					fields: fields
				}
			],
			primary_action: function() {
				const items = this.get_values()["items"];
				frappe.call({
					method: 'metactical.custom_scripts.sales_order.sales_order.change_warehouse',
					freeze: true,
					args: {
						'items': items
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
		dialog.show();
	},
	
	currency: function(frm){
		setTimeout(function(){
			frappe.after_ajax(function(){
				frm.fields_dict['currency_and_price_list'].collapse(0);
			});
		}, 1000);
	},
	
	setup(frm) {
		frm.set_indicator_formatter('item_code',
			function(doc) { return (doc.actual_qty>=doc.qty) ? "green" : "red" }
		);
    }
});
frappe.ui.form.on("Sales Order Item", {
	delivered_by_supplier: function(frm, cdt, cdn){
		if(frm.doc.docstatus == 1){
			var row = locals[cdt][cdn];
			return frm.call({
					method: "metactical.custom_scripts.sales_order.sales_order.get_bin_details",
					args:{
						"item_code": row.item,
						"sales_order": row.sales_order
					},
					callback: function(result){
						console.log(result)
					}
				});
		}
	},
	
	qty(frm) {
        cur_frm.refresh_field("items")
    }
});

erpnext.selling.SalesOrderController = class SalesOrderController extends erpnext.selling.SalesOrderController {
	customer_address(doc, dt, dn){
		// Metactical Customization: Add ability to change address even when submitted
		if(doc.docstatus == 1){
			erpnext.utils.get_address_display(this.frm, "customer_address");		
		}
		else{
			erpnext.utils.get_address_display(this.frm, "customer_address");
			erpnext.utils.set_taxes_from_address(this.frm, "customer_address", "customer_address", "shipping_address_name");
		}
	}
	
	warehouse(doc, cdt, cdn){
		var me = this;
		var item = frappe.get_doc(cdt, cdn);

		// check if serial nos entered are as much as qty in row
		if (item.serial_no) {
			let serial_nos = item.serial_no.split(`\n`).filter(sn => sn.trim()); // filter out whitespaces
			if (item.qty === serial_nos.length) return;
		}

		if (item.serial_no && !item.batch_no) {
			item.serial_no = null;
		}

		var has_batch_no;
		frappe.db.get_value('Item', {'item_code': item.item_code}, 'has_batch_no', (r) => {
			has_batch_no = r && r.has_batch_no;
			if(item.item_code && item.warehouse) {
				return this.frm.call({
					method: "erpnext.stock.get_item_details.get_bin_details_and_serial_nos",
					child: item,
					args: {
						item_code: item.item_code,
						warehouse: item.warehouse,
						has_batch_no: has_batch_no || 0,
						stock_qty: item.stock_qty,
						serial_no: item.serial_no || "",
					},
					callback:function(r){
						if (in_list(['Delivery Note', 'Sales Invoice'], doc.doctype)) {
							if (doc.doctype === 'Sales Invoice' && (!doc.update_stock)) return;
							if (has_batch_no) {
								me.set_batch_number(cdt, cdn);
								me.batch_no(doc, cdt, cdn);
							}
						}
					}
				});
			}
		})
		
		// Metactical Customization: Load reserved qty in sales order
		var row = locals[cdt][cdn];
		if (row.item_code && row.warehouse) {
			return this.frm.call({
					method: "metactical.custom_scripts.sales_order.sales_order.get_bin_details",
					child: row,
					args: {
						item_code: row.item_code,
						warehouse: row.warehouse,
					},
					callback:function(r){
						console.log(r);
						row.sal_reserved_qty =  r.message['reserved_qty'];
						row.ais_is_stock_item = r.message["is_stock_item"]
						refresh_field("sal_reserved_qty", cdn, "items");
						refresh_field("ais_is_stock_item", cdn, "items");
					}
				});
		}
	}
	
	customer(frm){
		// Metactical Customization: Clear company address to force them to enter manually
		var me = this;
		var args = {"company_address": ''}
		get_party_details(this.frm, null, null, function() {
			me.apply_price_list();
			frappe.after_ajax(function(){
				setTimeout(
					function(){
						cur_frm.fields_dict["contact_info"].collapse(0);
						cur_frm.set_value("company_address", '');
					}, 2000);
			});
		});
	}
	
	close_sales_order(){
		// Metactical Customization: Pop up to enter reason for closing
		var me = this;
		frappe.prompt([
				{'fieldname': 'close_reason', 'fieldtype': 'Small Text', 'label': 'Enter Reason', 'reqd': 1}
			],
			function(values){
				frappe.call({
					'method': 'metactical.custom_scripts.sales_order.sales_order.save_close_reason',
					'args': {
						'docname': cur_frm.docname,
						'close_reason': values.close_reason
					},
					'callback': function(r){
						me.frm.cscript.update_status("Close", "Closed")
					}
				});
			},
			'Please enter the reason for closing the Sales Order.',
			'Close'
		)
	}
};

extend_cscript(cur_frm.cscript, new erpnext.selling.SalesOrderController({frm: cur_frm}));

//Metactical Customization: Replace erpnext.utils.get_party_details
var get_party_details = function(frm, method, args, callback) {
	if (!method) {
		method = "erpnext.accounts.party.get_party_details";
	}

	if (args) {
		if (in_list(['Sales Invoice', 'Sales Order', 'Delivery Note'], frm.doc.doctype)) {
			if (frm.doc.company_address && (!args.company_address)) {
				args.company_address = '';
			}
		}

		if (in_list(['Purchase Invoice', 'Purchase Order', 'Purchase Receipt'], frm.doc.doctype)) {
			if (frm.doc.shipping_address && (!args.shipping_address)) {
				args.shipping_address = frm.doc.shipping_address;
			}
		}
	}

	if (!args) {
		if ((frm.doctype != "Purchase Order" && frm.doc.customer)
			|| (frm.doc.party_name && in_list(['Quotation', 'Opportunity'], frm.doc.doctype))) {

			let party_type = "Customer";
			if (frm.doc.quotation_to && frm.doc.quotation_to === "Lead") {
				party_type = "Lead";
			}

			args = {
				party: frm.doc.customer || frm.doc.party_name,
				party_type: party_type,
				price_list: ''
			};
		} else if (frm.doc.supplier) {
			args = {
				party: frm.doc.supplier,
				party_type: "Supplier",
				bill_date: frm.doc.bill_date,
				price_list: frm.doc.buying_price_list
			};
		}

		if (in_list(['Sales Invoice', 'Sales Order', 'Delivery Note'], frm.doc.doctype)) {
			if (!args) {
				args = {
					party: frm.doc.customer || frm.doc.party_name,
					party_type: 'Customer'
				}
			}
			if (frm.doc.company_address && (!args.company_address)) {
				args.company_address = '';
			}

			if (frm.doc.shipping_address_name &&(!args.shipping_address_name)) {
				args.shipping_address_name = frm.doc.shipping_address_name;
			}
		}

		if (in_list(['Purchase Invoice', 'Purchase Order', 'Purchase Receipt'], frm.doc.doctype)) {
			if (!args) {
				args = {
					party: frm.doc.supplier,
					party_type: 'Supplier'
				}
			}

			if (frm.doc.shipping_address && (!args.shipping_address)) {
				args.shipping_address = frm.doc.shipping_address;
			}
		}

		if (args) {
			args.posting_date = frm.doc.posting_date || frm.doc.transaction_date;
		}
	}
	if (!args || !args.party) return;

	if (frappe.meta.get_docfield(frm.doc.doctype, "taxes")) {
		if (!erpnext.utils.validate_mandatory(frm, "Posting / Transaction Date",
			args.posting_date, args.party_type=="Customer" ? "customer": "supplier")) return;
	}

	if (!erpnext.utils.validate_mandatory(frm, "Company", frm.doc.company, args.party_type=="Customer" ? "customer": "supplier")) {
		return;
	}

	args.currency = frm.doc.currency;
	args.company = frm.doc.company;
	args.doctype = frm.doc.doctype;
	frappe.call({
		method: method,
		args: args,
		callback: function(r) {
			if (r.message) {
				frm.supplier_tds = r.message.supplier_tds;
				frm.updating_party_details = true;
				frappe.run_serially([
					() => frm.set_value(r.message),
					() => {
						frm.updating_party_details = false;
						if (callback) callback();
						frm.refresh();
						erpnext.utils.add_item(frm);
					}
				]);
			}
		}
	});
}
