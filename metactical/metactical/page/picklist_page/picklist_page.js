frappe.provide('metactical.pick_list');

frappe.pages['picklist-page'].on_page_load = function(wrapper) {
	frappe.pick_list = new PicklistPage(wrapper);
}

class PicklistPage{
	constructor(wrapper) {
		this.make_page(wrapper);
	}
	
	make_page(wrapper){
		var me = this;
		this.page = frappe.ui.make_app_page({
			parent: wrapper,
			title: 'Electronic Picklist',
			single_column: true
		});
		this.wrapper = $(wrapper).find(".page-content");
		this.load_home();
		
		//Remove picked by
		$(document).on('page-change', function() {
			if(metactical.pick_list.current_pick != undefined){
				me.close_pick_list(metactical.pick_list.current_pick);
			}
		});
		
		window.onbeforeunload = function(){
			if(metactical.pick_list.current_pick != undefined){
				me.close_pick_list(metactical.pick_list.current_pick).then(()=>{
					//Just so it waits
					setTimeout(1000);
				});
			}
		}
	}
	
	load_home(){
		const me = this;
		this.wrapper.html(frappe.render_template("picklist_page"));
		this.$single_order_button = this.wrapper.find("#single_order_button");
		this.$list_orders_btn = this.wrapper.find('#list_orders_button');
		this.$list_totes_btn = this.wrapper.find('#multi_order_button');
		this.$selected_warehouse = this.wrapper.find('#selected_warehouse');
		this.$selected_source = this.wrapper.find('#selected_source');
		this.$user_name = this.wrapper.find('#user_name');
		this.$user_name.html('Welcome ' + frappe.session.user_fullname);
		this.get_defaults().then((ret) => {
			me.$selected_warehouse.html(ret.message.default_warehouse);
			me.$selected_source.html(ret.message.default_location);
			metactical.pick_list.selected_warehouse = ret.message.default_warehouse;
			metactical.pick_list.selected_source = ret.message.default_location;
			me.load_summary();
		});
		this.$single_order_button.on('click', function(){
			metactical.pick_list.is_tote = false;
			frappe.run_serially([
				() => me.list_orders()
			]);
		});
		this.$list_orders_btn.on('click', function(){
			metactical.pick_list.is_tote = false;
			frappe.run_serially([
				() => me.list_orders()
			]);
		});
		this.$list_totes_btn.on('click', function(){
			metactical.pick_list.is_tote = true;
			me.list_totes();
		});
		this.$selected_warehouse.on('click', function(){
			me.change_warehouse()
		});
		this.$selected_source.on('click', function(){
			me.change_source()
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
	
	change_source() {
		var me = this;
		frappe.prompt(
			[{"fieldtype": "Link", "fieldname": "source", "options": "Lead Source", "label": 'Source'}],
			function(values){
				if(typeof values.source == "undefined"){
					values.source = "All";
				}
				me.$selected_source.html(values.source);
				metactical.pick_list.selected_source = values.source
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
				"warehouse": metactical.pick_list.selected_warehouse,
				"source": metactical.pick_list.selected_source
			},
			"callback": function(ret){
				me.$summary.ready_to_ship.html(ret.message.ready_to_ship);
				me.$summary.ready_to_pick.html(ret.message.items_to_pick);
				me.$summary.rush_orders.html(ret.message.rush_orders);
				me.$summary.same_address.html(ret.message.same_address);
			}
		});
	}
	
	list_totes(){
		const me = this;
		metactical.pick_list.selected_totes = [];
		metactical.pick_list.is_tote = true;
		frappe.call({
			"method": "metactical.metactical.page.picklist_page.picklist_page.get_totes",
			"args": {
				"warehouse": metactical.pick_list.selected_warehouse
			},
			"freeze": true,
			"callback": function(ret){
				me.wrapper.html(frappe.render_template('totes_list', {"totes": ret.message}));
				me.wrapper.find('.start-picking-btn').hide(); //Hide start picking button
				me.wrapper.find('.back-to-home').on('click', function(){
					me.load_home();
				});
				me.wrapper.find('.refresh-totes').on('click', function(){
					me.list_totes();
				});
				me.tote_barcode = frappe.ui.form.make_control({
					parent: $('.tote-barcode'),
					df: {
						fieldtype: 'Data',
						fieldname: 'tote-barcode',
						placeholder: 'Scan Tote'
					},
					render_input: true
				});
				me.tote_barcode.set_focus();
				me.wrapper.find('.tote-barcode').on('keypress', function(){
					if(event.keyCode == 13){
						let tote_barcode = me.tote_barcode.get_value();
						if(tote_barcode != ""){
							me.scan_tote(tote_barcode);
						}
					}
				});
				me.wrapper.find('.tote-barcode').on('focusout', function(){
					let tote_barcode = me.tote_barcode.get_value();
					if(tote_barcode != ""){
						me.scan_tote(tote_barcode);
					}
				})
				me.wrapper.find('.tote-list-div').on('click', function(){
					let tote_div = $(this);
					let tote = unescape(tote_div.attr('data-tote-list'));
					me.scan_tote(tote, false);
				});
				me.wrapper.find('.tote-check').on('click', function(){
					let tote_div = $(this);
					let tote = unescape(tote_div.attr('data-tote-list'));
					me.scan_tote(tote, false);
				});
				me.wrapper.find('.start-picking-btn').on('click', function(){
					//me.list_tote_items();
					me.list_multi_orders(metactical.pick_list.selected_source);
				});
			}
		});
	}
	
	scan_tote(barcode, scanned=true){
		var me = this;
		let found_barcode = me.wrapper.find('[value="' + barcode + '"]');
		let selected_totes = metactical.pick_list.selected_totes;
		let start_picking_btn = me.wrapper.find('.start-picking-btn');
		if(found_barcode.length > 0){
			if(scanned){
				frappe.utils.play_sound("alert");
			}
			if(found_barcode.is(':checked')){
				found_barcode.prop("checked", false);
				selected_totes.pop(barcode);
			}
			else{
				found_barcode.prop("checked", true);
				if(selected_totes.indexOf(barcode) == -1){
					selected_totes.push(barcode);
				}
			}
			me.tote_barcode.set_value("");
		}
		else{
			frappe.utils.play_sound("error");
			frappe.show_alert({
				message: __("Error: Tote not in list of available totes."),
				indicator: "orange"
			});
		}
		if(selected_totes.length == 0){
			start_picking_btn.hide();
		}
		else{
			start_picking_btn.show();
		}
	}
	
	list_multi_orders(source="All", searched=false, pl_filter=""){
		const me = this;
		if(source == ""){
			source = "All"
		}
		if(searched == true){
			if(pl_filter != ""){
				let pick_lists = metactical.pick_list.pick_lists;
				let filtered_pl = [];
				for(let i in pick_lists){
					if(pick_lists[i].name.search(pl_filter) != -1){
						filtered_pl.push(pick_lists[i]);
					}
				}
				me.wrapper.html(frappe.render_template('orders_list_multiorder', {
					'pick_lists': filtered_pl, 
					'selected_pick_lists': metactical.pick_list.selected_pick_lists}));
				me.setup_multi_order_events(pl_filter, source);
			}
		}
		else{
			let limit = metactical.pick_list.selected_totes.length;
			metactical.pick_list.selected_pick_lists = [];
			frappe.call({
				"method": "metactical.metactical.page.picklist_page.picklist_page.get_pick_lists",
				"freeze": true,
				"args": {
					"warehouse": metactical.pick_list.selected_warehouse,
					"filters": "",
					"source": source
				},
				"callback": function(ret){
					metactical.pick_list.pick_lists = ret.message;
					me.wrapper.html(frappe.render_template('orders_list_multiorder', {
						pick_lists: ret.message, selected_pick_lists: []}));
					me.setup_multi_order_events("", source);
				}
			});
		}
	}
	
	setup_multi_order_events(pl_filter="", pl_source="All"){
		var me = this;
		me.wrapper.find('.start-picking-btn').hide();
		me.wrapper.find('.refresh-orders').on('click', function(){
			me.list_multi_orders();
		});
		me.wrapper.find('.back-to-tote').on('click', function(){
			me.list_totes();
		});
		me.pl_source = frappe.ui.form.make_control({
			parent: $('.pl-multi-source'),
			df: {
				fieldname: "pl_multi_source",
				fieldtype: "Link",
				options: "Lead Source",
				placeholder: pl_source,
				change: function(){
					me.list_multi_orders(me.pl_source.get_value());
				}
			},
			render_input: true
		});
		let pl_placeholder = "Search Pick List";
		if(pl_filter != ""){
			pl_placeholder = pl_filter;
		}
		me.pl_barcode = frappe.ui.form.make_control({
			parent: $('.pl-multi-barcode'),
			df: {
				fieldname: 'pl_multi_barcode',
				fieldtype: 'Data',
				placeholder: pl_placeholder
			},
			render_input: true
		});
		me.wrapper.find('.pl-list-div').on('click', function(){
			let pl_div = $(this);
			let pick_list = unescape(pl_div.attr('data-pick-list'));
			me.select_pick(pick_list, false);
		});
		me.wrapper.find('.pl-check').on('click', function(){
			let pl_div = $(this);
			let pick_list = unescape(pl_div.attr('data-pick-list'));
			me.select_pick(pick_list, false);
		});
		me.wrapper.find('.pl-multi-barcode').on('keypress', function(){
			if(event.keyCode == 13){
				let barcode = me.pl_barcode.get_value();
				me.list_multi_orders(pl_source, true, barcode);
			}
		});
		me.wrapper.find('.pl-multi-barcode').on('focusout', function(){
			let barcode = me.pl_barcode.get_value();
			me.list_multi_orders(pl_source, true, barcode);
		});
		me.wrapper.find('.start-picking-btn').on('click', function(){
			me.list_tote_items();
		});
	}
	
	select_pick(barcode, scanned=true){
		var me = this;
		let found_barcode = me.wrapper.find('[value="' + barcode + '"]');
		let selected_pl = metactical.pick_list.selected_pick_lists;
		let start_picking_btn = me.wrapper.find('.start-picking-btn');
		if(found_barcode.length > 0){
			if(scanned){
				frappe.utils.play_sound("alert");
			}
			if(found_barcode.is(':checked')){
				found_barcode.prop("checked", false);
				selected_pl.pop(barcode);
			}
			else{
				if(selected_pl.indexOf(barcode) == -1){
					let no_of_totes = metactical.pick_list.selected_totes.length;
					let no_of_pls = selected_pl.length;
					if(no_of_pls < no_of_totes){
						found_barcode.prop("checked", true);
						selected_pl.push(barcode);
					}
					else{
						frappe.utils.play_sound("error");
						frappe.show_alert({
							message: __("Error: Number of selected pick lists is more than selected totes"),
							indicator: "orange"
						});
					}
				}
			}
			me.pl_barcode.set_value("");
		}
		else{
			frappe.utils.play_sound("error");
			frappe.show_alert({
				message: __("Error: Pick List not in list of available Pick Lists"),
				indicator: "orange"
			});
		}
		if(selected_pl.length == 0){
			start_picking_btn.hide();
		}
		else{
			start_picking_btn.show();
		}
	}
	
	list_tote_items(){
		const me = this;
		metactical.pick_list.picked_items = [];
		metactical.pick_list.items_to_pick = [];
		frappe.call({
			method: "metactical.metactical.page.picklist_page.picklist_page.get_tote_items",
			args: {
				"warehouse": metactical.pick_list.selected_warehouse,
				"pick_lists": metactical.pick_list.selected_pick_lists,
				"user": frappe.session.user,
				"totes": metactical.pick_list.selected_totes
			},
			freeze: true,
			callback: function(ret){
				if(ret.message == 'None'){
					console.log('No orders');
				}
				else{
					me.wrapper.html(frappe.render_template('totes_items_list'));
					metactical.pick_list.items_to_pick = ret.message.items;
					//Assign totes to pick lists
					if(metactical.pick_list.items_to_pick.length > 0){
						let items_to_pick = metactical.pick_list.items_to_pick;
						for(let i in ret.message.pick_lists){
							let current_pick_list = ret.message.pick_lists[i];
							let current_tote = metactical.pick_list.selected_totes[i];
							for(let j in items_to_pick){
								let item = items_to_pick[j];
								if(item.pick_list == current_pick_list){
									item["tote"] = current_tote
								}
							}
						}
					}
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
	
	list_orders(filter=''){
		const me = this;
		frappe.call({
			"method": "metactical.metactical.page.picklist_page.picklist_page.get_pick_lists",
			"args": {
				"warehouse": metactical.pick_list.selected_warehouse,
				"filters": filter,
				"source": metactical.pick_list.selected_source
			},
			"freeze": true,
			"callback": function(ret){
				let selected_source = 'Source';
				if(metactical.pick_list.selected_source != "All"){
					selected_source = metactical.pick_list.selected_source;
				}
				me.wrapper.html(frappe.render_template('orders_list', {"pick_lists": ret.message}));
				me.pl_barcode = frappe.ui.form.make_control({
					parent: $('.pl-barcode'),
					df: {
						fieldname: 'pl_barcode',
						fieldtype: 'Data',
						placeholder: 'Search Pick List'
					},
					render_input: true
				});
				me.pl_source = frappe.ui.form.make_control({
					parent: $('.pl-source'),
					df: {
						fieldname: 'source',
						fieldtype: 'Link',
						options: 'Lead Source',
						placeholder: selected_source,
						change: function(){
							let source = me.pl_source.get_value();
							if(source != ""){
								metactical.pick_list.selected_source = source;
								me.list_orders();
							}
						}
					},
					render_input: true
				})
				
				// Set default location
				/*let current_location = me.pl_source.get_value();
				if(current_location == "" && metactical.pick_list.default_location != "" &&
					metactical.pick_list.selected_source == "All"){
						metactical.pick_list.selected_source = metactical.pick_list.default_location;
						me.pl_source.set_value(metactical.pick_list.default_location);
				}*/
				
				me.pl_barcode.set_value(filter);
				me.pl_barcode.set_focus();
				/*if(metactical.pick_list.selected_source != "All"){
					me.pl_source.set_value(metactical.pick_list.selected_source);
				}*/
				me.orders = me.wrapper.find('.orders-container');
				me.orders.on('click', '.order-list-div', function(){
					var order = $(this);
					metactical.pick_list.current_pick = unescape(order.attr('data-pick-list'));
					me.list_single_totes();
				})
				me.wrapper.find('.back-to-home').on('click', function(){
					me.load_home();
				});
				me.wrapper.find('.refresh-orders').on('click', function(){
					me.list_orders();
				});
				me.wrapper.find('.pl-barcode').on('keypress', function(){
					if(event.keyCode == 13){
						var barcode = $('input[data-fieldname="pl_barcode"]').val();
						me.list_orders(filter=barcode);
					}
				});
				me.wrapper.find('.pl-barcode').on('focusout', function(){
					var barcode = $('input[data-fieldname="pl_barcode"]').val();
					if(barcode != ''){
						me.list_orders(filter=barcode);
					}
				});
				me.wrapper.find('.pl-source').on('focusout', function(){
					
				});
			}
		});
	}
	
	list_single_totes(){
		const me = this;
		metactical.pick_list.selected_totes = [];
		metactical.pick_list.available_totes = [];
		frappe.call({
			"method": "metactical.metactical.page.picklist_page.picklist_page.get_totes",
			"freeze": true, 
			"args": {"warehouse": metactical.pick_list.selected_warehouse},
			"callback": function(ret){
				metactical.pick_list.available_totes = ret.message;
				me.wrapper.html(frappe.render_template('totes_single_list', 
					{"totes": ret.message}));
				me.tote_barcode = frappe.ui.form.make_control({
					parent: $('.tote-barcode'),
					df: {
						fieldtype: "Data",
						fieldname: "tote_barcode",
						placeholder: "Scan/Search Tote"
					},
					render_input: true
				});
				me.tote_barcode.set_focus();
				me.wrapper.find('.tote-barcode').on('keypress', function(){
					if(event.keyCode == 13){
						let scanned_tote = me.tote_barcode.get_value();
						let available_totes = metactical.pick_list.available_totes;
						if(scanned_tote != "" && available_totes.indexOf(scanned_tote) != -1){
							metactical.pick_list.selected_totes.push(scanned_tote);
							me.list_items(metactical.pick_list.current_pick);
						}
					}
				});
				me.wrapper.find('.tote-barcode').on('focusout', function(){
					let scanned_tote = me.tote_barcode.get_value();
					let available_totes = metactical.pick_list.available_totes;
					if(scanned_tote != "" && available_totes.indexOf(scanned_tote) != -1){
						metactical.pick_list.selected_totes.push(scanned_tote);
						me.list_items(metactical.pick_list.current_pick);
					}
				});
				me.wrapper.find('.totes-list-div').on('click', 
					function(){
						metactical.pick_list.selected_totes.push(unescape($(this).attr('data-tote')));
						me.list_items(metactical.pick_list.current_pick);
				});
				me.wrapper.find('.back-to-pick').on('click', function(){
					me.list_orders();
				});
				me.wrapper.find('.refresh-totes').on('click', function(){
					me.list_totes();
				});
			}
		});
	}
	
	list_items(pick_list){
		const me = this;
		var selected_warehouse = me.$selected_warehouse.text();
		metactical.pick_list.picked_items = [];
		metactical.pick_list.items_to_pick = [];
		metactical.pick_list.current_pick = pick_list;
		frappe.call({
			"method": "metactical.metactical.page.picklist_page.picklist_page.get_items",
			"freeze": true,
			"args": {
				"warehouse": selected_warehouse,
				"pick_list": pick_list,
				"user": frappe.session.user,
				"tote": metactical.pick_list.selected_totes[0]
			},
			"callback": function(ret){
				if(ret.message == 'None'){
					console.log('No orders');
				}
				else if(ret.message == 'Already Picked'){
						frappe.msgprint({
							title: 'Already, being picked',
							message: 'This order is already beeing picked. Please choose another one',
							primary_action: {
								label: 'Reload List',
								action: function(values){
									me.list_orders();
									this.hide();
								}
							}
					});
				}
				else{
					metactical.pick_list.items_to_pick = ret.message.items;
					me.wrapper.html(frappe.render_template('items_list',
						{"pick_list_name": metactical.pick_list.current_pick}));
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
		if(strip(items_template) == ""){
			this.wrapper.find('.to-pick-ul').html(frappe.render_template('submit_button'));
			this.wrapper.find('.submit-pick').on('click', function(event){
				event.preventDefault();
				me.submit_pick_list();
			});
			this.wrapper.find('.submit-pick-link').on('click', function(event){
				event.preventDefault();
			});
		}
		else{
			//this.wrapper.find('.to-pick-ul').html(frappe.render_template('submit_button'));
			this.wrapper.find('.to-pick-ul').html(items_template);
		}
		
		//this.wrapper.find('#picked-items-div').hide();
		this.$back_to_list = this.wrapper.find('.back-to-list');
		this.$load_picked = this.wrapper.find('#picked-items-btn');
		this.$back_to_pick = this.wrapper.find('#back-to-pick');
		this.submit_partial = this.wrapper.find('.submit-items-btn');
		//If it's tote then go back to totes list otherwise back to pick list
		if(metactical.pick_list.is_tote){
			this.$back_to_list.on('click', function(){
				me.clear_totes_picklists().then(() => {
					me.list_totes();
				});
			});
		}
		else{
			this.$back_to_list.on('click', function(){
				me.close_pick_list(metactical.pick_list.current_pick).then(() => {
					me.list_totes();
				});
			});
		}
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
	
	trigger_picked(picked_item, from_barcode=false, tote_no=null){
		const me = this;
		let is_tote = metactical.pick_list.is_tote;
		for(let row in metactical.pick_list.items_to_pick){
			var item = metactical.pick_list.items_to_pick[row];
			if(item.item_code == picked_item.item_code && item.pick_list == picked_item.pick_list){
				if(from_barcode){
					me.pick_item(item, 1);
					break;
				}
				else{
					var to_pick = item.qty - 1;
					var pick_qty = new frappe.ui.Dialog({
						'fields': [
							{"fieldtype": "HTML", "fieldname": "ht"}
						],
						'primary_action_label': 'Add',
						'secondary_action_label': 'Cancel',
						'primary_action': function(){
							let to_pick_f = pick_qty.fields_dict.ht.$wrapper.find('.to_pick');
							if(parseFloat(to_pick_f.val()) > (item.qty)){
								frappe.throw("Error: You've picked more items than required");
							}
							else if(parseFloat(to_pick_f.val()) <= 0){
								frappe.throw("Error: You haven't picked any items");
							}
							else{
								me.pick_item(item, to_pick_f.val());
								pick_qty.hide();
							}
						},
						'secondary_action': function(){
							pick_qty.hide();
						}
					});
					let to_pick_vars = {'to_pick': to_pick, 'is_tote': is_tote};
					if(is_tote == true){
						to_pick_vars["tote_no"] = tote_no;
					}
					pick_qty.fields_dict.ht.$wrapper.html(frappe.render_template('picked_qty', 
								to_pick_vars));
					pick_qty.show();
					
					//Add listeners for add substract fields
					let add_btn = pick_qty.fields_dict.ht.$wrapper.find('.pick-add');
					let sub_btn = pick_qty.fields_dict.ht.$wrapper.find('.pick-sub');
					let to_pick_field = pick_qty.fields_dict.ht.$wrapper.find('.to_pick');
					let items_remaining = pick_qty.fields_dict.ht.$wrapper.find('.items-remaining');
					let tote_barcode = pick_qty.fields_dict.ht.$wrapper.find('.tote-barcode');
					add_btn.on('click', function(event){
						event.preventDefault();
						to_pick_field.val(parseFloat(to_pick_field.val()) + 1);
						items_remaining.html(parseFloat(items_remaining.text()) - 1);				
					});
					sub_btn.on('click', function(){
						event.preventDefault();
						to_pick_field.val(parseFloat(to_pick_field.val()) - 1);
						items_remaining.html(parseFloat(items_remaining.text()) + 1);				
					});
					to_pick_field.on('change', function(){
						items_remaining.html(item.qty - parseFloat(to_pick_field.val()));
					});
					tote_barcode.on('change', function(){
						if(tote_barcode.val() == tote_no){
							let to_pick_f = pick_qty.fields_dict.ht.$wrapper.find('.to_pick');
							if(parseFloat(to_pick_f.val()) > (item.qty)){
								frappe.throw("Error: You've picked more items than required");
							}
							else if(parseFloat(to_pick_f.val()) <= 0){
								frappe.throw("Error: You haven't picked any items");
							}
							else{
								me.pick_item(item, to_pick_f.val());
								pick_qty.hide();
							}
						}
						else{
							frappe.utils.play_sound("error");
							frappe.show_alert({
								message:"Error: Wrong tote scanned",
								indicator: "orange"
							});
						}
					});
					setTimeout(function(){tote_barcode.focus();}, 500);
					break;
				}
			}
		}
	}
	
	pick_item(item, qty){
		var me = this;
		let existing_item = metactical.pick_list.picked_items.filter((itm) => itm.item_code == item.item_code && itm.pick_list == item.pick_list);
		let to_pick_item = metactical.pick_list.items_to_pick.filter((itm) => itm.item_code == item.item_code && itm.pick_list == item.pick_list);
		if(existing_item.length > 0){
			existing_item[0].picked_qty += parseFloat(qty);
		}
		else{
			var new_item = $.extend(true, {}, item);
			new_item.picked_qty = parseFloat(qty);
			metactical.pick_list.picked_items.push(new_item);					
		}
		to_pick_item[0].qty = to_pick_item[0].qty - parseFloat(qty);
		me.load_to_pick();
		me.load_picked();
		me.item_barcode.set_focus();
	}
	
	create_listeners(){
		const me = this;
		this.items = this.wrapper.find('.to-pick-ul');
		this.picked = this.wrapper.find('.picked-ul');
		this.items.on('click', '.item-li', function(){
			var item = $(this);
			var picked = {
				"item_code":  unescape(item.attr('data-item-code')),
				"picked_qty": parseFloat(item.find(".pick-qty").html()),
				"pick_list": unescape(item.attr('data-pick-list'))
			}
			let tote = item.attr('data-tote');
			let is_tote = false;
			if(typeof tote !== 'undefined' && tote !== false){
				is_tote = true;
			}
			me.trigger_picked(picked, false, tote);
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
									"picked_qty": 1,
									"pick_list": to_pick[i].pick_list
								}
								me.trigger_picked(picked, true);
								frappe.utils.play_sound("alert");
							}
						}
					}
					if(barcode_found){
						me.item_barcode.set_value("");
					}else{
						me.item_barcode.set_value("");
						frappe.utils.play_sound("error");
						frappe.show_alert({
							message: __("No items found. Scan barcode again."),
							indicator: 'orange'
						});
					}
				}
			}
		});
		this.submit_partial.on('click', function(event){
			event.preventDefault();
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
			if(item_exists.length == 0){
				let new_item = $.extend(true, {}, item);
				new_item.picked_qty = 0;
				metactical.pick_list.picked_items.push(new_item);
			}
		}
		frappe.call({
			"method": "metactical.metactical.page.picklist_page.picklist_page.submit_pick_list",
			"freeze": true,
			"args": {
				"items": metactical.pick_list.picked_items,
			},
			"callback": function(ret){
				frappe.show_alert({
					message: __('Pick List Submitted'),
					indicator: 'green'
				});
				metactical.pick_list.picked_items = [];
				metactical.pick_list.to_pick = [];
				metactical.pick_list.current_pick = '';
				if(metactical.pick_list.is_tote){
					me.list_totes();
				}
				else{
					me.list_orders();
				}
			}
		});
	}
	
	close_pick_list(pick_list){
		//Remove the user from unsubmitted pick list
		return frappe.call({
			method: "metactical.metactical.page.picklist_page.picklist_page.close_pick_list",
			freeze: true,
			args: {
				"pick_list": pick_list
			}
		});
	}
	
	clear_totes_picklists(){
		//Clear totes and users from unsubmitted pick lists
		let pick_lists = [];
		let items_to_pick = metactical.pick_list.items_to_pick;
		let picked_items = metactical.pick_list.picked_items
		for(let i in items_to_pick){
			if(pick_lists.indexOf(items_to_pick[i].pick_list) == -1){
				pick_lists.push(items_to_pick[i].pick_list);
			}
		}
		for(let i in picked_items){
			if(pick_lists.indexOf(picked_items[i].pick_list) == -1){
				pick_lists.push(picked_items[i].pick_list);
			}
		}
		return frappe.call({
			method: "metactical.metactical.page.picklist_page.picklist_page.clear_totes_picklist",
			freeze: true,
			args: {
				"totes": metactical.pick_list.selected_totes,
				"pick_lists": pick_lists
			}
		});
	}
}
