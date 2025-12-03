frappe.provide('metactical.pick_list');

frappe.pages['picklist-page'].on_page_load = function(wrapper) {
	frappe.pick_list = new PicklistPage(wrapper);
}

class PicklistPage{
	constructor(wrapper) {
		this.make_page(wrapper).then(() => {
			this.setupPageCloseListeners();
			this.setupPageReturnListeners();
		});
	}
	
	make_page(wrapper){
		var me = this;
		this.page = frappe.ui.make_app_page({
			parent: wrapper,
			title: 'Electronic Picklist',
			single_column: true
		});
		this.wrapper = $(wrapper).find(".page-content");
		
		return new Promise((resolve) => {
			me.load_home();
			
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
			
			this.setupPlTextEditHandler(); // make the handler available for all views
			
			// Resolve the promise after everything is set up
			resolve();
		});
	}
	
	setupPlTextEditHandler() {
		const me = this;
		$(document).off('click.metactical', '.edit-pl-text').on('click.metactical', '.edit-pl-text', function (e) {
			e.preventDefault();
			const $btn = $(this);
			const pickList = $btn.data('pickList') || (window.metactical?.pick_list?.current_pick);
			if (!pickList) {
				frappe.msgprint(__('Missing Pick List name.'));
				return;
			}
			const $box = $(`#pl-text-container-${pickList}`);
			const currentText = ($box.text() || $btn.data('currentText') || '').trim();

			const d = new frappe.ui.Dialog({
				title: __('Add/Edit Note'),
				fields: [{ fieldtype: 'Small Text', fieldname: 'pl_text', label: __('Note'), default: currentText }],
				primary_action_label: __('Save'),
				primary_action(values) {
					frappe.call({
						method: "metactical.metactical.page.picklist_page.picklist_page.update_pl_text",
						freeze: true,
						args: { pick_list: pickList, pl_text: values.pl_text || "" },
						callback: function () {
							const txt = (values.pl_text || "").trim();
							if (txt) {
								$box.text(txt).show();
							} else {
								$box.text('').hide();
							}
							// keep button’s data-current-text in sync
							$btn.data('currentText', txt);
							frappe.show_alert({ message: __('Note saved'), indicator: 'green' });
							d.hide();
						}
					});
				}
			});
			d.show();
		});
	}

	load_home(){
		const me = this;
		this.wrapper.html(frappe.render_template("picklist_page"));
		this.$single_order_button = this.wrapper.find("#single_order_button");
		this.$list_orders_btn = this.wrapper.find('#list_orders_button');
		this.$list_totes_btn = this.wrapper.find('#multi_order_button');
		this.$selected_warehouse = this.wrapper.find('#selected_warehouse');
		this.$selected_source = this.wrapper.find('#selected_source');
		this.$selected_country = this.wrapper.find('#selected_country');
		this.$user_name = this.wrapper.find('#user_name');
		this.$user_name.html('Welcome ' + frappe.session.user_fullname);
		this.get_defaults().then((ret) => {
			console.log("Ret: ", ret);
			let default_location = ret.message.default_location;
			let last_country = ret.message.last_country;

			if (ret.message.last_source && ret.message.last_source != ""){
				default_location = ret.message.last_source
			}
			else if(default_location == "" || default_location == null){
				default_location = "All"
			}

			if(last_country == "" || last_country == null){
				last_country = ret.message.default_country || "All";
			}

			me.$selected_warehouse.html(ret.message.default_warehouse);
			me.$selected_source.html(default_location);
			me.$selected_country.html(last_country);

			metactical.pick_list.selected_warehouse = ret.message.default_warehouse;
			metactical.pick_list.selected_source = default_location;
			metactical.pick_list.no_for_manual = ret.message.no_for_manual;
			metactical.pick_list.selected_country = last_country;

			if(ret.message.sort_order) {
				metactical.pick_list.order_sort_order = ret.message.sort_order;
			}
			else{
				metactical.pick_list.order_sort_order = "desc";
			}

			if(ret.message.sort_by) {
				metactical.pick_list.order_sort_by = ret.message.sort_by;
			}
			else{
				metactical.pick_list.order_sort_by = "qty_item";
			}

			// Initialize to pick and picked items
			if(metactical.pick_list.picked_items == undefined || metactical.pick_list.items_to_pick == undefined){
				metactical.pick_list.picked_items = [];
				metactical.pick_list.items_to_pick = [];
			}

			me.load_summary();
		});
		this.$single_order_button.on('click', function(){
			metactical.pick_list.selection_type = "Single";
			metactical.pick_list.is_tote = false;
			frappe.run_serially([
				() => me.list_orders()
			]);
		});
		this.$list_orders_btn.on('click', function(){
			metactical.pick_list.selection_type = "Single"
			metactical.pick_list.is_tote = false;
			frappe.run_serially([
				() => me.list_orders()
			]);
		});
		this.$list_totes_btn.on('click', function(){
			metactical.pick_list.selection_type = "Multi";
			metactical.pick_list.is_tote = true;
			//me.list_totes();
			me.list_multi_orders(metactical.pick_list.selected_source);
		});
		this.$selected_warehouse.on('click', function(){
			me.change_warehouse()
		});
		this.$selected_source.on('click', function(){
			me.change_source()
		});
		this.$selected_country.on('click', function(){
			me.change_country()
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
				frappe.call({
					method: "metactical.metactical.page.picklist_page.picklist_page.update_user_filters",
					args: {
						user: frappe.session.user,
						field_name: "last_warehouse",
						field_value: values.warehouse
					},
					callback: function(r) {
						me.$selected_warehouse.html(values.warehouse);
						metactical.pick_list.selected_warehouse = values.warehouse
						me.load_summary();
					}
				});
			},
			'Change Warehouse',
			'Change' 
		)
	}
	
	change_source() {
		var me = this;
		
		// Create the dialog
		var d = new frappe.ui.Dialog({
			title: 'Change Source',
			fields: [
				{
					"fieldtype": "Link", 
					"fieldname": "source", 
					"options": "Lead Source", 
					"label": 'Source'
				},
			],
			primary_action_label: 'Change',
			primary_action: function(values) {
				if(typeof values.source == "undefined"){
					values.source = "All";
				}
				frappe.call({
					method: "metactical.metactical.page.picklist_page.picklist_page.update_user_filters",
					args: {
						user: frappe.session.user,
						field_name: "last_source",
						field_value: values.source
					},
					callback: function(r) {
						if (r.message && r.message.status === "success") {
							console.log("Source filter saved:", values.source);
						}

						me.$selected_source.html(values.source);
						metactical.pick_list.selected_source = values.source
						me.load_summary();
					}
					});
				d.hide();
			}
		});

		// Add a custom "All" button in the dialog's standard footer
		d.set_secondary_action_label("All Sources");
		d.set_secondary_action(function() {
			// Set the source to "All" and trigger the same save functionality
			frappe.call({
				method: "metactical.metactical.page.picklist_page.picklist_page.update_user_filters",
				args: {
					user: frappe.session.user,
					field_name: "last_source",
					field_value: "All"
				},
				callback: function(r) {
					if (r.message && r.message.status === "success") {
						console.log("Source filter saved: All");
					}

					me.$selected_source.html("All");
					metactical.pick_list.selected_source = "All";
					me.load_summary();
				}
			});
			d.hide();
		});

		// Show the dialog
		d.show();
	}

	change_country() {
		var me = this;
		frappe.prompt(
			[{
					"fieldtype": "Select", 
					"fieldname": "country", 
					"options": "All\nCanada\nUnited States", 
					"label": 'Country'
			}],
			function(values){
				if(typeof values.country == "undefined"){
					values.country = "All";
				}
				frappe.call({
					method: "metactical.metactical.page.picklist_page.picklist_page.update_user_filters",
					freeze: true,
					args: {
						"user": frappe.session.user,
						"field_name": "last_country",
						"field_value": values.country
					},
					callback: function(r){
						me.$selected_country.html(values.country);
						metactical.pick_list.selected_country = values.country;
						me.load_summary();
					}
				});
			},
			'Change Order Country',
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
				"source": metactical.pick_list.selected_source,
				"country": metactical.pick_list.selected_country
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
		metactical.pick_list.unassigned_picklists = metactical.pick_list.selected_pick_lists.slice();
		metactical.pick_list.assigned_picklists = [];
		frappe.call({
			"method": "metactical.metactical.page.picklist_page.picklist_page.get_totes",
			"args": {
				"warehouse": metactical.pick_list.selected_warehouse,
				"pick_lists": metactical.pick_list.selected_pick_lists
			},
			"freeze": true,
			"callback": function(ret){
				let totes = ret.message.totes;
				let partial_totes = ret.message.partial_totes;
				metactical.pick_list.assigned_picklists = partial_totes.slice();

				if(partial_totes.length > 0){
					for(let row in partial_totes) {
						metactical.pick_list.selected_totes.push(partial_totes[row].tote_name);
						let index = metactical.pick_list.unassigned_picklists.indexOf(partial_totes[row].pick_list);
						if(index > -1) {
							metactical.pick_list.unassigned_picklists.splice(index, 1);
						}
					}
				}

				me.wrapper.html(frappe.render_template('totes_list', {"totes": totes, 
					"partial_totes": partial_totes}));
				
				me.wrapper.find('.start-picking-btn').hide(); //Hide start picking button
				
				me.wrapper.find('.back-to-home').on('click', function(){
					//me.load_home();
					me.list_multi_orders(metactical.pick_list.selected_source, undefined, undefined, undefined, undefined, true);
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
						let tote_check = $('div[data-tote-list="' + tote_barcode + '"]').find(".tote-check");
						if(tote_barcode != ""){
							me.scan_tote(tote_barcode, true, tote_check);
						}
					}
				});
				me.wrapper.find('.tote-barcode').on('focusout', function(){
					let tote_barcode = me.tote_barcode.get_value();
					let tote_check = $('div[data-tote-list="' + tote_barcode + '"]').find(".tote-check");
					if(tote_barcode != ""){
						me.scan_tote(tote_barcode, false, tote_check);
					}
				})
				me.wrapper.find('.tote-list-div').on('click', function(){
					let tote_div = $(this);
					let tote = unescape(tote_div.attr('data-tote-list'));
					let selected_totes = metactical.pick_list.selected_totes;
					let tote_check = tote_div.find(".tote-check");
					me.scan_tote(tote, false, tote_check);
				});
				me.wrapper.find('.start-picking-btn').on('click', function(){
					me.list_tote_items();
					//me.list_multi_orders(metactical.pick_list.selected_source);
				});

				setTimeout(function(){
					if(metactical.pick_list.selected_pick_lists.length == 
						metactical.pick_list.selected_totes.length
					){
						me.wrapper.find('.start-picking-btn').show();
					}
				}, 200);
			}
		});
	}
	
	scan_tote(barcode, scanned=true, tote_check=""){
		let me = this;
		let found_barcode = me.wrapper.find('[value="' + barcode + '"]');
		let selected_totes = metactical.pick_list.selected_totes;
		let start_picking_btn = me.wrapper.find('.start-picking-btn');
		let selected_picklists = metactical.pick_list.selected_pick_lists;
		if(found_barcode.length > 0){
			if(scanned){
				frappe.utils.play_sound("alert");
			}
			if(selected_totes.indexOf(barcode) == -1){
				if(selected_totes.length < selected_picklists.length){
					frappe.prompt(
						[
							{
								"fieldname": "pick_list",
								"label": "Unassigned Pick Lists",
								"fieldtype": "Select",
								"options": metactical.pick_list.unassigned_picklists.join("\n"),
								"reqd": 1,
							}
						],
						(values) => {
							selected_totes.push(barcode);
							tote_check.prop("checked", true);
							let index = metactical.pick_list.unassigned_picklists.indexOf(values.pick_list);
							if(index > -1){
								metactical.pick_list.unassigned_picklists.splice(index, 1);
							}
							metactical.pick_list.assigned_picklists.push({"tote_name": barcode, "pick_list": values.pick_list});
							me.wrapper.find(`#picklist-${barcode}`).html(`(${values.pick_list})`);
							me.show_hide_pick_button();
						},
						"Please select a Pick List",
						"Select"
					);
				}
				else{
					frappe.show_alert({
						message: __("Error: The selected number of Totes is greater than the selected number of Picklists"),
						indicator: "orange"
					});
				}
			}
			else {
				let assigned_picklists = metactical.pick_list.assigned_picklists;
				for(let i in assigned_picklists){
					let assigned_picklist = assigned_picklists[i];
					if(assigned_picklist.tote_name == barcode){
						let index = assigned_picklists.indexOf(assigned_picklist);
						if(index > -1){
							assigned_picklists.splice(index, 1);
						}

						index = selected_totes.indexOf(barcode);
						if(index > -1){
							selected_totes.splice(index, 1);
						}

						metactical.pick_list.unassigned_picklists.push(assigned_picklist.pick_list);
						tote_check.prop("checked", false);
						me.wrapper.find(`#picklist-${barcode}`).html("");
						break;
					}
				}
				this.show_hide_pick_button();
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
		
	}

	show_hide_pick_button(){
		let selected_totes = metactical.pick_list.selected_totes;
		let start_picking_btn = this.wrapper.find('.start-picking-btn');
		let selected_picklists = metactical.pick_list.selected_pick_lists;
		if(selected_totes.length == selected_picklists.length){
			start_picking_btn.show();
		}
		else{
			start_picking_btn.hide();
		}
	}
	
	list_multi_orders(source="All", searched=false, pl_filter="", sort_by="qty_item", sort_order="desc", is_reload=false){
		const me = this;
		// If it's a reload either by clicking refresh or going back, load the
		// previous sort values
		sort_by = metactical.pick_list.order_sort_by;
		sort_order = metactical.pick_list.order_sort_order;

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
				me.setup_multi_order_events(pl_filter, source, sort_by, sort_order);
			}
		}
		else{
			metactical.pick_list.selected_pick_lists = [];
			frappe.call({
				"method": "metactical.metactical.page.picklist_page.picklist_page.get_pick_lists",
				"freeze": true,
				"args": {
					"warehouse": metactical.pick_list.selected_warehouse,
					"country": metactical.pick_list.selected_country,
					"filters": "",
					"source": source,
					"sort_by": sort_by,
					"sort_order": sort_order
				},
				"callback": function(ret){
					metactical.pick_list.pick_lists = ret.message;
					me.wrapper.html(frappe.render_template('orders_list_multiorder', {
						pick_lists: ret.message, selected_pick_lists: []}));
					me.setup_multi_order_events("", source, sort_by, sort_order);
				}
			});
		}
	}
	
	setup_multi_order_events(pl_filter="", pl_source="All", sort_by="qty_item", sort_order="desc"){
		var me = this;
		me.wrapper.find('.start-picking-btn').hide();
		me.wrapper.find('.refresh-orders').on('click', function(){
			me.list_multi_orders(pl_source, false, pl_filter, sort_by, sort_order, true);
		});
		me.wrapper.find('.back-to-home').on('click', function(){
			me.load_home();
		});

		// Initialize with the global selected source if available
		if (metactical.pick_list && metactical.pick_list.selected_source) {
			pl_source = metactical.pick_list.selected_source;
		}

		me.pl_source = frappe.ui.form.make_control({
			parent: $('.pl-multi-source'),
			df: {
				fieldname: "pl_multi_source",
				fieldtype: "Link",
				options: "Lead Source",
				placeholder: pl_source,
				default: pl_source !== "All" ? pl_source : "",
				change: function(){
					const sourceValue = me.pl_source.get_value() || "All";

					if(pl_source == metactical.pick_list.selected_source){
						return
					}
					
					// Update global selected source
					metactical.pick_list.selected_source = sourceValue;
					
					// Save the filter preference in the backend
					frappe.call({
						method: "metactical.metactical.page.picklist_page.picklist_page.update_user_filters",
						args: {
							user: frappe.session.user,
							field_name: "last_source",
							field_value: sourceValue
						},
						callback: function(r) {
							if (r.message && r.message.status === "success") {
								console.log("Source filter saved:", sourceValue);
							}
						}
					});

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

		let sort_labels = {
			"qty_item": "QtyItems",
			"locations": "Locations",
			"order_date": "Order Date"
		}

		me.sort_selector = new frappe.ui.SortSelector({
			parent: $('.pl-multi-filters'),
			args: {
				options: [
					{
						fieldname: "qty_items",
						label: "QtyItems"
					},
					{
						fieldname: "locations",
						label: "Locations"
					},
					{
						fieldname: "order_date",
						label: "Order Date"
					}
				],
				sort_by: sort_by,
				sort_by_label: sort_labels[sort_by],
				sort_order: sort_order
			},
			sort_by: sort_by,
			sort_order: sort_order,
			onchange: function(){
				let barcode = $('input[data-fieldname="pl_multi_barcode"]').val();
				let sort_order = me.sort_selector.sort_order;
				let sort_by = me.sort_selector.sort_by;
				let field_name = '';
				let field_value = '';

				if(sort_by != metactical.pick_list.order_sort_by){
					field_name = 'sort_by';
					field_value = sort_by;
					metactical.pick_list.order_sort_by = me.sort_selector.sort_by;
				}
				else if(sort_order != metactical.pick_list.order_sort_order){
					field_name = 'sort_order';
					field_value = sort_order;
					metactical.pick_list.order_sort_order = me.sort_selector.sort_order;
				}

				frappe.call({
					method: "metactical.metactical.page.picklist_page.picklist_page.update_user_filters",
					freeze: true,
					args: {
						"user": frappe.session.user,
						"field_name": field_name,
						"field_value": field_value
					},
					callback: function(r){
						me.list_multi_orders(pl_source, false, barcode, sort_by, sort_order);
					}
				});
			}
		});
		me.wrapper.find('.pl-list-div').on('click', function(){
			let pl_div = $(this);
			let pick_list = unescape(pl_div.attr('data-pick-list'));
			let pl_check = $(this).find('.pl-check');
			let picked_pls = metactical.pick_list.selected_pick_lists;
			if(picked_pls.indexOf(pick_list) != -1) {
				pl_check.prop("checked", false);
				me.select_pick(pick_list, false);
			}
			else{
				pl_check.prop("checked", true);
				me.select_pick(pick_list, false);
			}
		});

		// After control is rendered, explicitly set the value
		if (pl_source && pl_source !== "All") {
			me.pl_source.set_value(pl_source);
		}

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
			//me.list_tote_items();
			me.list_totes();
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
			if(selected_pl.indexOf(barcode) == -1){
				selected_pl.push(barcode);
			}
			else{
				let index = selected_pl.indexOf(barcode);
				if(index > -1){
					selected_pl.splice(index, 1);
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
				"totes": metactical.pick_list.selected_totes,
				"assigned_picklists": metactical.pick_list.assigned_picklists
			},
			freeze: true,
			callback: function(ret){
				if(ret.message == 'None'){
					console.log('No orders');
				}
				else{
					me.wrapper.html(frappe.render_template('totes_items_list', {"pl_texts": ret.message.pl_texts}));
					metactical.pick_list.items_to_pick = ret.message.items;
					metactical.pick_list.picked_items = ret.message.partially_picked;
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
	
	list_orders(filter='', sort_by="qty_item", sort_order="desc", is_reload=false){
		const me = this;

		sort_by = metactical.pick_list.order_sort_by;
		sort_order = metactical.pick_list.order_sort_order;
		let selected_source = 'All';

		// Initialize with the global selected source if available
		if (metactical.pick_list && metactical.pick_list.selected_source) {
			selected_source = metactical.pick_list.selected_source;
		}
		console.log("Got to here");
		frappe.call({
			"method": "metactical.metactical.page.picklist_page.picklist_page.get_pick_lists",
			"args": {
				"warehouse": metactical.pick_list.selected_warehouse,
				"country": metactical.pick_list.selected_country,
				"filters": filter,
				"source": metactical.pick_list.selected_source,
				"sort_by": sort_by,
				"sort_order": sort_order
			},
			"freeze": true,
			"callback": function(ret){
				console.log("PL: ", ret);
				let selected_source = 'All';
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
						default: selected_source !== "All" ? selected_source : "",
						change: function(){
							// let source = me.pl_source.get_value();
							// if(source != ""){
							// 	metactical.pick_list.selected_source = source;
							// 	me.list_orders(filter=barcode, undefined, undefined, true);
							// }

							let source = me.pl_source.get_value();

							if(source == metactical.pick_list.selected_source) {
								return
							}
							
							// Update global selected source
							metactical.pick_list.selected_source = source;
							
							// Save the filter preference in the backend
							frappe.call({
								method: "metactical.metactical.page.picklist_page.picklist_page.update_user_filters",
								args: {
									user: frappe.session.user,
									field_name: "last_source",
									field_value: source
								},
								callback: function(r) {
									if (r.message && r.message.status === "success") {
										console.log("Source filter saved:", source);
									}
								}
							});
							
							// Update the list with the new filter
							me.list_orders(filter=filter, undefined, undefined, true);
						}
					},
					render_input: true
				});
				
				let sort_labels = {
					"qty_item": "QtyItems",
					"locations": "Locations",
					"order_date": "Order Date"
				}

				me.sort_selector = new frappe.ui.SortSelector({
					parent: $('.pl-sort-selector'),
					args: {
						options: [
							{
								fieldname: "qty_item",
								label: "QtyItems"
							},
							{
								fieldname: "locations",
								label: "Locations"
							},
							{
								fieldname: "order_date",
								label: "Order Date"
							}
						],
						sort_by: sort_by,
						sort_by_label: sort_labels[sort_by],
						sort_order: sort_order
					},
					sort_by: sort_by,
					sort_order: sort_order,
					onchange: function(){
						let barcode = $('input[data-fieldname="pl_barcode"]').val();
						let sort_by = me.sort_selector.sort_by;
						let sort_order = me.sort_selector.sort_order;
						// metactical.pick_list.order_sort_by = me.sort_selector.sort_by;
						// metactical.pick_list.order_sort_order = me.sort_selector.sort_order;

						//let barcode = $('input[data-fieldname="pl_multi_barcode"]').val();
						// let sort_order = me.sort_selector.sort_order;
						// let sort_by = me.sort_selector.sort_by;
						let field_name = '';
						let field_value = '';

						if(sort_by != metactical.pick_list.order_sort_by){
							field_name = 'sort_by';
							field_value = sort_by;
							metactical.pick_list.order_sort_by = me.sort_selector.sort_by;
						}
						else if(sort_order != metactical.pick_list.order_sort_order){
							field_name = 'sort_order';
							field_value = sort_order;
							metactical.pick_list.order_sort_order = me.sort_selector.sort_order;
						}

						frappe.call({
							method: "metactical.metactical.page.picklist_page.picklist_page.update_user_filters",
							freeze: true,
							args: {
								"user": frappe.session.user,
								"field_name": field_name,
								"field_value": field_value
							},
							callback: function(r){
								me.list_orders(barcode, sort_by, sort_order);
							}
						});
					}
				});
				
				if (selected_source && selected_source !== "All") {
					me.pl_source.set_value(selected_source);
				}

				me.pl_barcode.set_value(filter);
				me.pl_barcode.set_focus();
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
					me.list_orders(undefined, undefined, undefined, true);
				});
				me.wrapper.find('.pl-barcode').on('keypress', function(){
					if(event.keyCode == 13){
						var barcode = $('input[data-fieldname="pl_barcode"]').val();
						me.list_orders(filter=barcode, undefined, undefined, true);
					}
				});
				me.wrapper.find('.pl-barcode').on('focusout', function(){
					var barcode = $('input[data-fieldname="pl_barcode"]').val();
					if(barcode != '' && barcode != filter){
						me.list_orders(filter=barcode, undefined, undefined, true);
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
			"args": {
				"warehouse": metactical.pick_list.selected_warehouse,
				"pick_lists": [metactical.pick_list.current_pick]
			},
			"callback": function(ret){
				let available_totes = []

				if(ret.message.partial_totes && ret.message.partial_totes.length > 0){
					available_totes = [ret.message.partial_totes[0].tote_name];
				}
				else{
					available_totes = ret.message.totes;
				}
				metactical.pick_list.available_totes = available_totes;
				me.wrapper.html(frappe.render_template('totes_single_list', 
					{"totes": available_totes}));
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
				me.wrapper.find('.back-to-pick').on('click', function(){
					me.list_orders(undefined, undefined, undefined, true);
				});
				me.wrapper.find('.refresh-totes').on('click', function(){
					me.list_single_totes();
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
									me.list_orders(undefined, undefined, undefined, true);
									this.hide();
								}
							}
					});
				}
				else{
					metactical.pick_list.items_to_pick = ret.message.items;
					if(ret.message.partially_picked){
						metactical.pick_list.picked_items = ret.message.partially_picked;
					}
					me.wrapper.html(frappe.render_template('items_list',
						{"pick_list_name": metactical.pick_list.current_pick, "pl_text": ret.message.pl_text}));
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
					me.list_single_totes();
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

								// If the qty is more than specified in settings, then
								// can scan multiple items at same time
								if(to_pick[i].qty >= metactical.pick_list.no_for_manual){
									me.trigger_picked(picked, false);
								}
								else{
									me.trigger_picked(picked, true);
								}
								frappe.utils.play_sound("alert");
							}
						}
					}
					if(barcode_found){
						me.item_barcode.set_value("");
					}else{
						me.item_barcode.set_value("");
						frappe.utils.play_sound("error");
						frappe.msgprint("No items found. Please scan barcode again.", "Wrong Barcode");
					}
				}
			}
		});
		this.submit_partial.on('click', function(event){
			event.preventDefault();
			me.submit_pick_list();
		});
	}
	
	submit_pick_list(){
		const me = this;
		let all_items_picked = true;
		// Check that all items have been picked, otherwise raise an error
		for (let item of metactical.pick_list.items_to_pick) {
			if (item.qty > 0) {
				all_items_picked = false;
				break;
			}
		}
		
		frappe.call({
			"method": "metactical.metactical.page.picklist_page.picklist_page.mark_as_picked",
			"freeze": true,
			"args": {
				"picked_items": metactical.pick_list.picked_items,
				"user": frappe.session.user,
				"all_items": metactical.pick_list.items_to_pick
			},
			"callback": function(ret){
				frappe.show_alert({
					message: __('Pick List Submitted'),
					indicator: 'green'
				});
				metactical.pick_list.picked_items = [];
				metactical.pick_list.to_pick = [];
				metactical.pick_list.current_pick = '';
				if(metactical.pick_list.selection_type == "Multi"){
					me.list_multi_orders(metactical.pick_list.selected_source, undefined, undefined, undefined, undefined, true);
				}
				else{
					me.list_orders(undefined, undefined, undefined, true);
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

	setupPageCloseListeners() {
		const me = this;
		
		// Initialize global variables if they're undefined
		if (!metactical.pick_list) {
			metactical.pick_list = {};
		}
		
		if (!metactical.pick_list.items_to_pick) {
			metactical.pick_list.items_to_pick = [];
		}
		
		if (!metactical.pick_list.picked_items) {
			metactical.pick_list.picked_items = [];
		}
		
		// Helper function to check if cleanup is needed
		const needsCleanup = function() {
			// Always get fresh values from the global object
			const itemsToPick = metactical.pick_list.items_to_pick || [];
			const pickedItems = metactical.pick_list.picked_items || [];
			const currentPick = metactical.pick_list.current_pick;
			
			return (itemsToPick.length > 0 || pickedItems.length > 0 || currentPick !== undefined);
		};
		
		// Helper function to perform cleanup
		const performCleanup = function() {
			const currentPick = metactical.pick_list.current_pick;
			
			// First clear totes
			me.clear_totes_picklists();
			
			// Then close pick list if there is one
			if (currentPick !== undefined) {
				me.close_pick_list(currentPick);
			}
		};
		
		// Handle tab/window close
		window.addEventListener('beforeunload', function(e) {
			if (needsCleanup()) {
				// Cancel the event
				e.preventDefault();
				// Chrome requires returnValue to be set
				e.returnValue = 'You have unsaved changes. Are you sure you want to leave?';
				
				// Attempt to clean up
				performCleanup();
				
				// Return a string to show dialog box in most browsers
				return 'You have unsaved changes. Are you sure you want to leave?';
			} else {
				console.log("Page close - no cleanup needed");
			}
		});
		
		// Handle page navigation within Frappe
		$(document).on('page-change', function() {
			if (needsCleanup()) {
				performCleanup();
			}
		});
		
		// Handle browser back button
		window.addEventListener('popstate', function() {
			if (needsCleanup()) {
				performCleanup();
			}
		});
		
		// Handle user session timeout/expiry
		$(document).on('session_expired', function() {
			if (needsCleanup()) {
				performCleanup();
			}
		});
	}

	setupPageReturnListeners() {
		const me = this;
		
		// Set up router change handler
		frappe.router.on('change', function() {
			if (frappe.get_route_str() === 'picklist-page' && me.page_initialized) {
				me.refresh_data();
			}
		});
		
		// This is called when the page is shown
		$(document).on('page-show', function(e, page_name) {
			if (page_name === 'picklist-page' && me.page_initialized) {
				me.refresh_data();
			}
		});
		
		// Set flag once page is fully initialized
		this.page_initialized = true;
	}
	
	refresh_data() {
		
		if (metactical.pick_list.current_pick !== undefined) {
			this.close_pick_list(metactical.pick_list.current_pick);
		}
		// Reload necessary data when returning to the page
		this.load_home();
	}
}
