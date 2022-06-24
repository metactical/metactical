frappe.provide('metactical.pick_list');

frappe.pages['picklist-page'].on_page_load = function(wrapper) {
	new PicklistPage(wrapper)
}

class PicklistPage{
	constructor(wrapper) {
		this.make_page(wrapper);
	}
	
	make_page(wrapper){
		this.page = frappe.ui.make_app_page({
			parent: wrapper,
			title: 'Electronic Picklist',
			single_column: true
		});
		this.wrapper = $(wrapper).find(".page-content");
		this.load_home();		
	}
	
	load_home(){
		const me = this;
		this.wrapper.html(frappe.render_template("picklist_page"));
		this.$single_order_button = this.wrapper.find("#single_order_button");
		this.$list_orders_btn = this.wrapper.find('#list_orders_button');
		this.$selected_warehouse = this.wrapper.find('#selected_warehouse');
		this.$user_name = this.wrapper.find('#user_name');
		this.$user_name.html('Welcome ' + frappe.session.user_fullname);
		this.get_defaults().then((ret) => {
			me.$selected_warehouse.html(ret.message.default_warehouse);
			metactical.pick_list.selected_warehouse = ret.message.default_warehouse;
			me.load_summary();
		});
		this.$single_order_button.on('click', function(){
			frappe.run_serially([
				() => me.list_orders()
			]);
		});
		this.$list_orders_btn.on('click', function(){
			frappe.run_serially([
				() => me.list_orders()
			]);
		});
		this.$selected_warehouse.on('click', function(){
			me.change_warehouse()
		});
	}
	
	get_defaults() {
		return frappe.call("metactical.metactical.page.picklist_page.picklist_page.get_defaults", {"user": frappe.session.user})
	}
	
	change_warehouse() {
		var me = this;
		frappe.prompt(
			[{"fieldtype": "Link", "fieldname": "warehouse", "options": "Warehouse", "label": 'Warehouse'}],
			function(values){
				me.$selected_warehouse.html(values.warehouse);
				metactical.pick_list.selected_warehouse = values.warehouse
				me.load_summary();
			},
			'Change Warehouse',
			'Change' 
		)
	}
	
	load_summary(){
		var me = this;
		this.$summary = {};
		this.$summary.ready_to_ship = this.wrapper.find('#ready_to_ship');
		this.$summary.ready_to_pick = this.wrapper.find('#ready_to_pick');
		this.$summary.rush_orders = this.wrapper.find('#rush_orders');
		this.$summary.same_address = this.wrapper.find('#same_address');
		frappe.call({
			"method": "metactical.metactical.page.picklist_page.picklist_page.load_summary",
			"freeze": true,
			"args": {
				"warehouse": metactical.pick_list.selected_warehouse
			},
			"callback": function(ret){
				console.log(ret);
				me.$summary.ready_to_ship.html(ret.message.ready_to_ship);
				me.$summary.ready_to_pick.html(ret.message.items_to_pick);
				me.$summary.rush_orders.html(ret.message.rush_orders);
				me.$summary.same_address.html(ret.message.same_address);
			}
		})
	}
	
	list_orders(){
		const me = this;
		frappe.call({
			"method": "metactical.metactical.page.picklist_page.picklist_page.get_pick_lists",
			"args": {
				"warehouse": metactical.pick_list.selected_warehouse
			},
			"freeze": true,
			"callback": function(ret){
				console.log(ret);
				me.wrapper.html(frappe.render_template('orders_list', {"pick_lists": ret.message}));
				me.orders = me.wrapper.find('.orders-container');
				me.orders.on('click', '.order-list-div', function(){
					var order = $(this);
					var pick_list = unescape(order.attr('data-pick-list'));
					me.list_items(pick_list);
				})
				me.wrapper.find('#back-to-home').on('click', function(){
					me.load_home();
				});
			}
		});
	}
	
	list_items(pick_list){
		const me = this;
		var selected_warehouse = me.$selected_warehouse.text();
		metactical.pick_list.picked_items = [];
		metactical.pick_list.items_to_pick = [];
		frappe.call({
			"method": "metactical.metactical.page.picklist_page.picklist_page.get_items",
			"freeze": true,
			"args": {
				"warehouse": selected_warehouse,
				"pick_list": pick_list
			},
			"callback": function(ret){
				console.log({'ret': ret});
				if(ret.message == 'None'){
					console.log('No orders');
				}
				else{
					me.wrapper.html(frappe.render_template('items_list',
						{"pick_list_name": ret.message.name}));
					metactical.pick_list.items_to_pick = ret.message.items;
					me.item_barcode = frappe.ui.form.make_control({
						parent: $('.item-barcode'),
						df: {
							fieldname: "item_barcode",
							fieldtype: "Data",
							placeholder: "Item Barcode"
						},
						render_input: true
					});
					me.load_picked();
					me.load_to_pick();
					me.create_listeners();
					me.item_barcode.set_focus();
				}
			}
		});
	}
	
	load_to_pick(){
		const me = this;
		var items = metactical.pick_list.items_to_pick;
		var items_template = frappe.render_template('items_to_pick', {"items": items})
		console.log({"items_template": items_template});
		if(strip(items_template) == ""){
			this.wrapper.find('.to-pick-ul').html(frappe.render_template('submit_button'));
			this.wrapper.find('.submit-pick').on('click', function(){
				me.submit_pick_list();
			});
		}
		else{
			//this.wrapper.find('.to-pick-ul').html(frappe.render_template('submit_button'));
			this.wrapper.find('.to-pick-ul').html(items_template);
		}
		
		//this.wrapper.find('#picked-items-div').hide();
		this.$back_to_list = this.wrapper.find('#back-to-list');
		this.$load_picked = this.wrapper.find('#picked-items-btn');
		this.$back_to_pick = this.wrapper.find('#back-to-pick');
		this.submit_partial = this.wrapper.find('#submit-items-btn');
		
		this.$back_to_list.on('click', function(){
			me.list_orders();
		});
		this.$load_picked.on('click', function(){
			$('#pick-list-items-div').hide();
			$('#picked-items-div').show();
		});
		this.$back_to_pick.on('click', function(){
			$('#pick-list-items-div').show();
			$('#picked-items-div').hide();
		});
	}
	
	load_picked(){
		if(metactical.pick_list.picked_items.length > 0){
			var picked_template = frappe.render_template('picked_items_list', 
							{"items": metactical.pick_list.picked_items});
			this.wrapper.find('.picked-ul').html(picked_template);
		}
		else{
			this.wrapper.find('.picked-ul').html('');
		}
	}
	
	trigger_picked(picked_item){
		const me = this;
		for(let row in metactical.pick_list.items_to_pick){
			var item = metactical.pick_list.items_to_pick[row];
			if(item.item_code == picked_item.item_code){
				console.log({"item": item, "picked": picked_item});
				var to_pick = item.qty - 1;
				var pick_qty = new frappe.ui.Dialog({
					'fields': [
						{"fieldtype": "HTML", "fieldname": "ht"}
					],
					'primary_action_label': 'Add',
					'secondary_action_label': 'Cancel',
					'primary_action': function(){
						let existing_item = metactical.pick_list.picked_items.filter((itm) => itm.item_code == item.item_code);
						let to_pick_f = pick_qty.fields_dict.ht.$wrapper.find('.to_pick');
						if(parseFloat(to_pick_f.val()) > (item.qty)){
							frappe.throw("Error: You've picked more items than required");
						}
						else if(parseFloat(to_pick_f.val()) <= 0){
							frappe.throw("Error: You haven't picked any items");
						}
						else{
							if(existing_item.length > 0){
								existing_item[0].picked_qty += parseFloat(to_pick_f.val());
							}
							else{
								var new_item = $.extend(true, {}, item);
								new_item.picked_qty = parseFloat(to_pick_f.val());
								metactical.pick_list.picked_items.push(new_item);					
							}
							item.qty = item.qty - parseFloat(to_pick_f.val());
							me.load_to_pick();
							me.load_picked();
							pick_qty.hide();
							me.item_barcode.set_focus();
						}
					},
					'secondary_action': function(){
						pick_qty.hide();
					}
				});
				pick_qty.fields_dict.ht.$wrapper.html(frappe.render_template('picked_qty', {'to_pick': to_pick}));
				pick_qty.show();
				
				//Add listeners for add substract fields
				let add_btn = pick_qty.fields_dict.ht.$wrapper.find('.pick-add');
				let sub_btn = pick_qty.fields_dict.ht.$wrapper.find('.pick-sub');
				let to_pick_field = pick_qty.fields_dict.ht.$wrapper.find('.to_pick');
				let items_remaining = pick_qty.fields_dict.ht.$wrapper.find('.items-remaining');
				add_btn.on('click', function(){
					to_pick_field.val(parseFloat(to_pick_field.val()) + 1);
					items_remaining.html(parseFloat(items_remaining.text()) - 1);				
				});
				sub_btn.on('click', function(){
					to_pick_field.val(parseFloat(to_pick_field.val()) - 1);
					items_remaining.html(parseFloat(items_remaining.text()) + 1);				
				});
				to_pick_field.on('change', function(){
					items_remaining.html(item.qty - parseFloat(to_pick_field.val()));
				});
				break;
			}
		}
	}
	
	create_listeners(){
		const me = this;
		this.items = this.wrapper.find('.to-pick-ul');
		this.picked = this.wrapper.find('.picked-ul');
		this.items.on('click', '.item-li', function(){
			var item = $(this);
			var picked = {
				"item_code":  unescape(item.attr('data-item-code')),
				"picked_qty": parseFloat(item.find(".pick-qty").html())
			}
			me.trigger_picked(picked);
		});
		this.picked.on('click', '.item-li', function(){
			var cur_item = $(this);
			var item_code = unescape(cur_item.attr('data-item-code'));
			for(let i in metactical.pick_list.items_to_pick){
				let item = metactical.pick_list.items_to_pick[i];
				if(item.item_code == item_code){
					item.qty = parseFloat(item.qty) + 1;
				}
				break;
			}
			let picked = metactical.pick_list.picked_items.filter((itm) => itm.item_code == item_code);
			if(picked.length > 0){
				picked[0].picked_qty -= 1;
			}
			me.load_to_pick();
			me.load_picked();
		});
		this.item_barcode.$wrapper.on('keypress', function(){
			if(event.keyCode == 13){
				let value = me.item_barcode.get_value();
				let barcode_found = false;
				if (value != "" || value != 0) {
					var to_pick = metactical.pick_list.items_to_pick;
					for(var i in to_pick){
						let barcodes = to_pick[i].barcodes;
						if(barcodes.length > 0){
							if(barcodes.includes(value)){
								barcode_found = true
								var picked = {
									"item_code": to_pick[i].item_code,
									"picked_qty": 1
								}
								me.trigger_picked(picked);
							}
						}
					}
					if(barcode_found){
						me.item_barcode.set_value("");
						console.log({"barcode": value});
					}else{
						frappe.utils.play_sound("error");
						frappe.show_alert({
							message: __("No items found. Scan barcode again."),
							indicator: 'orange'
						});
					}
				}
			}
		});
		this.submit_partial.on('click', function(){
			if(metactical.pick_list.picked_items.length > 0){
				me.submit_pick_list();
			}
			else{
				frappe.show_alert('No items have been picked');
			}
		});
	}
	
	submit_pick_list(){
		const me = this;
		//Make the non-picked items zero
		for(var i in metactical.pick_list.items_to_pick){
			var item = metactical.pick_list.items_to_pick[i];
			var item_exists = metactical.pick_list.picked_items.filter((itm) => itm.item_code == item.item_code);
			console.log({"item_exists": item_exists});
			if(item_exists.length == 0){
				let new_item = $.extend(true, {}, item);
				new_item.picked_qty = 0;
				metactical.pick_list.picked_items.push(new_item);
			}
		}
		console.log({"picked": metactical.pick_list.picked_items});
		frappe.call({
			"method": "metactical.metactical.page.picklist_page.picklist_page.submit_pick_list",
			"freeze": true,
			"args": {
				"docname": metactical.pick_list.picked_items[0].parent,
				"items": metactical.pick_list.picked_items,
			},
			"callback": function(ret){
				frappe.show_alert({
					message: __('Pick List Submitted'),
					indicator: 'green'
				});
				metactical.pick_list.picked_items = [];
				metactical.pick_list.to_pick = [];
				me.list_orders();
			}
		});
	}
	
}
