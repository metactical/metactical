frappe.provide("metactical.packing_page");

frappe.pages['packing-page-v3'].on_page_load = function(wrapper) {
	// Check if user has permisssion to add
	frappe.call({
		method: "metactical.metactical.page.packing_page_v3.packing_page_v3.check_to_add_permission",
		freeze: true,
		callback: function(ret){
			metactical.packing_page.has_add_permission = ret.message;
		}
	});
	
	//Load the default warehouse
	metactical.packing_page.default_warehouse = "";
	frappe.call({
		method: "metactical.metactical.page.packing_page_v3.packing_page_v3.get_default_warehouse",
		freeze: true,
		callback: function(ret){
			metactical.packing_page.default_warehouse = ret.message;
			frappe.packing_slip = new PackingPage(wrapper);
		}
	});

	frappe.db.get_single_value("Packing Settings", "multi_pack_if_qty").then((res) => {
		metactical.packing_page.multi_pack_if_qty = res
	})
}

class PackingPage {
	constructor(wrapper) {
		this.page = wrapper.page;

		frappe.run_serially([
			() => this.make_page(wrapper),
			() => this.make_action_bar(),
			() => this.make_page_form(wrapper),
		]);
	}

	make_page(wrapper) {
		this.page = frappe.ui.make_app_page({
			parent: wrapper,
			title: "Packing Page V3",
			single_column: true,
		});
	}

	make_action_bar() {
		this.page.set_primary_action(
			"New",
			() => create_new(),
			"octicon octicon-plus"
		);

		this.page.set_secondary_action(
			"Refresh",
			() => refresh(),
			"octicon octicon-sync"
		);
	}

	make_page_form(wrapper) {
		this.wrapper = $(wrapper).find(".page-content");

		this.wrapper.html(
			frappe.render_template("packing_page_v3", {
				no_data_feedback: "Select Delivery Note",
				delivery_note: 0,
			})
		);
		
		//Hide the tote select until warehouse is selected
		$('.picklist-tote-wrapper').hide();

		// delivery note control
		let delivery_note_field = frappe.ui.form.make_control({
			parent: $(".delivery-note-wrapper"),
			df: {
				label: "Delivery Note",
				fieldname: "delivery_note",
				fieldtype: "Link",
				options: "Delivery Note",
				get_query: () => {
					return {
						filters: {
							docstatus: 0
						},
					};
				},
				change() {
					metactical.packing_page.fetch_dn_items();
					get_all_packed_items();
				},
			},
			render_input: true,
		});

		// item barcode control
		let item_barcode_field = frappe.ui.form.make_control({
			parent: $(".item-barcode-wrapper"),
			df: {
				label: "Item Barcode",
				fieldname: "item_barcode",
				fieldtype: "Data",
				change() {
					let value = item_barcode_field.get_value();
					if (value != "" || value != 0) {
						item_barcode_field.set_value("");
						metactical.packing_page.calc_packing_items(value);
					}
				},
			},
			render_input: true,
		});
		
		let selected_warehouse = frappe.ui.form.make_control({
			parent: $('.warehouse-wrapper'),
			df: {
				label: 'Warehouse',
				fieldtype: 'Link',
				fieldname: 'selected_warehouse',
				options: 'Warehouse',
				change(){
					$('.picklist-tote-wrapper').show();
				}
			},
			render_input: true
		});
		
		let tote_barcode_field = frappe.ui.form.make_control({
			parent: $('.picklist-tote-wrapper'),
			df: {
				label: "Tote Barcode",
				fieldname: "tote_barcode",
				fieldtype: "Data",
				get_query: function(){
					return {
						filters: [
							["warehouse", "=", selected_warehouse.get_value()],
							["current_delivery_note", "is", "set"]
						]
					}
				},
				change: function(){
					$('.picklist-tote-wrapper').on('keypress', function(event){
						//Only when enter is pressed
						if(event.keyCode == 13)
						{
							frappe.call({
								method: "metactical.metactical.page.packing_page_v3.packing_page_v3.get_delivery_from_tote",
								args: {
									tote: tote_barcode_field.get_value(),
									warehouse: selected_warehouse.get_value()
								},
								freeze: true,
								callback: function(ret){
									let is_tote = ret.message.is_tote;
									if(is_tote){
										delivery_note_field.set_value(ret.message.delivery_note);
									}
									else{
										frappe.throw("Error: No tote registered at warehouse with that name. Please check and try again.");
									}
								}
							});
						}
					});
				}
			},
			render_input:true
		});
		
		// Load default warehouse
		if(metactical.packing_page.default_warehouse != ""){
			$('[data-fieldname=selected_warehouse]').val(metactical.packing_page.default_warehouse);
			$('.picklist-tote-wrapper').show();
		}
	}
}

function get_all_packed_items(){
	// get packed items 
	let delivery_note = $('input[data-fieldname="delivery_note"]').val();
	metactical.packing_page.all_packed_items = [];
	
	frappe.call({
		method: "metactical.metactical.page.packing_page_v3.packing_page_v3.get_all_packed_items",
		freeze: true,
		args: {
			delivery_note: delivery_note
		},
		callback: function(ret){
			metactical.packing_page.all_packed_items = ret.message;
			console.log("All packed items: ", metactical.packing_page.all_packed_items);
		}
	});
}

function create_new() {
	$('input[data-fieldname="tote_barcode"]').val("");
	$('input[data-fieldname="delivery_note"]').val("");
	metactical.packing_page.fetch_dn_items(true);
}

function refresh() {
	$('input[data-fieldname="tote_barcode"]').val("");
	$('input[data-fieldname="delivery_note"]').val("");
	metactical.packing_page.fetch_dn_items(true);
}

function save_form() {
	let packed_items = metactical.packing_page.packed_items;
	
	let cur_doc = metactical.packing_page.cur_doc;
	cur_doc.items = packed_items;
	
	// Calculate weight
	var net_weight_pkg = 0;
	cur_doc.net_weight_uom = (packed_items && packed_items.length) ? packed_items[0].weight_uom : '';
	cur_doc.gross_weight_uom = cur_doc.net_weight_uom;

	for(var i=0; i<packed_items.length; i++) {
		var item = packed_items[i];
		if(item.weight_uom != cur_doc.net_weight_uom) {
			frappe.msgprint(__("The packed items have different weight UOM fwhich leads to incorrect (Total) Net Weight value.\
			 Therefore the weight will not be calculated for this Packing Slip."));
		}
		net_weight_pkg += flt(item.net_weight) * flt(item.qty);
	}

	cur_doc.net_weight_pkg = roundNumber(net_weight_pkg, 2);
	if(!flt(cur_doc.gross_weight_pkg)) {
		cur_doc.gross_weight_pkg = cur_doc.net_weight_pkg;
	}

	frappe.call({
		method: "frappe.desk.form.save.savedocs",
		args: {
			doc: cur_doc,
			action: "Submit"
		},
		freeze: true,
		btn: $(".primary-action"),
		callback: (r) => {
			// refresh();
			metactical.packing_page.packed_items = []
			$(".pack-items-btn").addClass("d-none")
			populate_dom()
			metactical.packing_page.fetch_dn_items(from_refresh = true);
			get_all_packed_items()
		},
		error: (r) => {
			console.error(r);
		},
	});
}

function count_pending_items() {
	const items = metactical.packing_page.pending_items;
	let count = 0;
	for (const item of items) {
		count += item.qty;
	}

	$(".pending-items-count").html(count + " Item(s) left");
}

function count_packed_items() {
	const items = metactical.packing_page.packed_items;
	let count = 0;

	$.each(metactical.packing_page.all_packed_items, function(i, item){
		$.each(item, function(j, props){
			count += props.qty;
		});
	})

	for (const item of items) {
		count += item.qty;
	}

	$(".packed-items-count").html(count + " Item(s) Packed");
}

function populate_pending_items() {
	const items = metactical.packing_page.pending_items;
	let items_template = "";
	if (items.length > 0) {
		items_template = frappe.render_template("pending_items_v3", {
			items: items,
		});
	}

	$(".pending-items-wrap").html(items_template);
}

function populate_current_item() {
	const item = metactical.packing_page.current_item;
	if (item.item_code) {
		let add_button_html = "Scan this item to move next "
		if(metactical.packing_page.has_add_permission){
			add_button_html += "or <button class='btn btn-default btn-sm' onClick='addOneItem()'>Click to Add</button> \
				<button class='btn btn-default btn-sm' onClick='addMultiple()'>Add Multiple</button>";
		}
		else{
			console.log(item.qty, metactical.packing_page.multi_pack_if_qty)
			if (item.qty > metactical.packing_page.multi_pack_if_qty) {
				add_button_html = "<button class='btn btn-default btn-sm' onClick='addMultiple()'>Add Multiple</button>";
			}
		}

		$(".cur-item-barcode").html("Packing Now " + item.item_barcode);
		$(".cur-item-scan-feedback").html(add_button_html);
		$(".cur-item-name").html(item.item_name);
		$(".cur-item-code").html(item.item_code);
		$(".cur-item-quantity-remaining").html(item.qty + " more to scan");
		$(".cur-item-image").attr("src", item.image);
		$(".cur-item-image").attr("alt", item.item_name);
	} else {
		$(".cur-item-barcode").html("");
		$(".cur-item-scan-feedback").html("");
		$(".cur-item-name").html("");
		$(".cur-item-code").html("");
		$(".cur-item-quantity-remaining").html("");
		$(".cur-item-image").attr("src", "");
		$(".cur-item-image").attr("alt", "");
	}
}

function packSelectedItems() {
	frappe.confirm(
		'Submit packing slip?',
		function(){
			metactical.packing_page.confirm_raised = false;
			save_form();
		},
		function(){
			metactical.packing_page.confirm_raised = false;
		}
	);
}

function populate_packed_items() {
	const items = metactical.packing_page.packed_items;
	let pending_items = metactical.packing_page.pending_items;
	let items_template = "";
	
	if(items.length > 0){
		items_template = frappe.render_template("packing_items_v3", {
			items: items,
		});
	} 
	
	if (pending_items.length == 0 && items.length > 0) {
		cur_page.page.page.set_primary_action(
			"Submit",
			() => save_form(),
			"octicon octicon-check"
		);
		
		//To fix bug(?) that loads confirmation multiple times
		if(pending_items.length == 0 && !metactical.packing_page.confirm_raised){
			metactical.packing_page.confirm_raised = true;
			frappe.confirm(
				'Submit packing slip?',
				function(){
					metactical.packing_page.confirm_raised = false;
					save_form();
				},
				function(){
					metactical.packing_page.confirm_raised = false;
				}
			);
		}
	} else {
		cur_page.page.page.set_primary_action(
			"New",
			() => create_new(),
			"octicon octicon-plus"
		);
	}
	$(".packed-items-wrap").html(items_template);
}

function re_generate_current_item(item = null) {
	pending_items = metactical.packing_page.pending_items;
	current_item = metactical.packing_page.current_item;
	if (!item) {
		for (var i = 0; i < pending_items.length; i++) {
			if (pending_items[i].item_code == current_item.item_code) {
				break;
			}
		}
		pending_items.splice(i, 1);
	}
	if (pending_items.length > 0) {
		if (item) {
			pending_items.forEach(function (row) {
				if (row.item_code == item) {
					metactical.packing_page.item_clicked = true;
					metactical.packing_page.current_item = row;
				}
			});
		} else {
			metactical.packing_page.current_item = pending_items[0];
		}
	} else {
		metactical.packing_page.current_item = {};
	}
	populate_dom();
	return;
}

function populate_dom() {
	count_pending_items();
	count_packed_items();
	populate_pending_items();
	if (metactical.packing_page.current_item) {
		populate_current_item();
	}
	populate_packed_items();
}

function addOneItem() {
	let cur_item = metactical.packing_page.current_item;
	if (cur_item.item_code && cur_item.item_barcode) {
		metactical.packing_page.item_clicked = true;
		metactical.packing_page.calc_packing_items(cur_item.item_barcode[0]);
	} else {
		frappe.show_alert({
			message: "Barcode not found",
			indicator: "red",
		});
	}
}

function addMultiple(){
	let cur_item = metactical.packing_page.current_item;
	frappe.prompt(
		[{"fieldtype": "Int", "fieldname": "amount", "label": "Number of Items to Add", "reqd": 1}],
		function(values){
			if(values.amount > cur_item.qty){
				frappe.throw("You can only add a maximum of " + cur_item.qty + " items");
			}
			else{
				metactical.packing_page.item_clicked = true;
				metactical.packing_page.calc_packing_items(cur_item.item_barcode[0], values.amount);
			}
		}
	);
}

function selectItem(item) {
	re_generate_current_item(item);
}

function ShowPackedItems() {
	var dialog = new frappe.ui.Dialog({
		title: "Packed Items",
		fields: [{
			fieldtype: "HTML",
			fieldname: "packed_item_detail",
		}]
	})

	let items = metactical.packing_page.all_packed_items;
	console.log(items)
	let packed_items = "";
	$.each(items, (packing_slip, item) => {
		packed_items += "<h4>" + packing_slip + "</h4>";
		packed_items += "<table class='table table-bordered'>";
		packed_items += "<thead><tr><th>Item Code</th><th>Item Name</th><th>Qty</th></tr></thead>";
		packed_items += "<tbody>";
		$.each(item, (i, props) => {
			packed_items += "<tr>";
			packed_items += "<td>" + props.item_code + "</td>";
			packed_items += "<td>" + props.item_name + "</td>";
			packed_items += "<td>" + props.qty + "</td>";
			packed_items += "</tr>";
		});
		packed_items += "</tbody>";
		packed_items += "</table>";
	});

	console.log(packed_items)

	dialog.fields_dict.packed_item_detail.$wrapper.html(packed_items);


	dialog.show()
}

metactical.packing_page.fetch_dn_items = (from_refresh = false) => {
	let delivery_note = $('input[data-fieldname="delivery_note"]').val();

	if (!delivery_note) {
		console.log("No delivery note selected");
		let template = frappe.render_template("packing_page_v3", {
			no_data_feedback: "Select Delivery Note",
			delivery_note: 0,
		});

		$(".packing-slip-wrapper").html(template);

		metactical.packing_page.pending_items = [];
		metactical.packing_page.current_item = {};
		metactical.packing_page.packed_items = [];
		populate_dom();
	} else {
		let new_packing_slip = frappe.model.get_new_doc(
			"Packing Slip",
			null,
			null,
			1
		);
		new_packing_slip.delivery_note = delivery_note;
		frappe.call({
			method: "runserverobj",
			args: {
				docs: new_packing_slip,
				method: "get_items"
			},
			callback: function (r) {
				let items = r.docs[0].items;
				let no_data_feedback = 0;
				metactical.packing_page.cur_doc = r.docs[0];

				// } else {
				frappe
					.call("metactical.api.packing_slip.get_item_master", {
						items: items,
					})
					.then((r) => {
						items = r.message;
						metactical.packing_page.current_item = []

						$(".packing-slip-wrapper").html(
							template =frappe.render_template("packing_page_v3", {
								no_data_feedback: 0,
								delivery_note: delivery_note,
							})
						);

						if (items.length == 0) 
							$(".current-section-title").html("<p class='no-items'>No items for this Delivery Note</p>")

						if (metactical.packing_page.item_clicked && !from_refresh) {
							//A hack to fix a bug(?) when the delivery note loaded. First click anywhere 
							//on the page calls refresh()
							metactical.packing_page.item_clicked = false;
						} else {
							metactical.packing_page.pending_items = items;
							metactical.packing_page.current_item = items[0];
							metactical.packing_page.packed_items = [];
						}

						populate_dom();
					});
				// }
			},
		});
	}
};

metactical.packing_page.calc_packing_items = (barcode, amount=1) => {
	let pending_items = metactical.packing_page.pending_items;

	if (barcode == "SKIP") {
		re_generate_current_item();
		return;
	}
	
	pending_items.forEach(function(cur_item){
		if (cur_item.item_barcode.indexOf(barcode) != -1) {
			metactical.packing_page.current_item = cur_item;
			if(amount > cur_item.qty){
				frappe.throw("You can only add a maximum of " + cur_item.qty + " items");
			}
			frappe.utils.play_sound("alert");
			
			let fields = [];

			console.log(cur_item);

			if (cur_item.net_weight === 0) {
				fields.push({
					fieldname: 'item_weight',
					label: 'Item weight',
					fieldtype: 'Float',
					reqd: 1
				});
			}

			if (cur_item.shipping_length === 0) {
				fields.push({
					fieldname: 'item_length',
					label: 'Shipping length',
					fieldtype: 'Float',
					reqd: 1
				});
			}

			if (cur_item.shipping_width === 0) {
				fields.push({
					fieldname: 'item_width',
					label: 'Shipping width',
					fieldtype: 'Float',
					reqd: 1
				});
			}

			if (cur_item.shipping_height === 0) {
				fields.push({
					fieldname: 'item_height',
					label: 'Shipping height',
					fieldtype: 'Float',
					reqd: 1
				});
			}

			if (fields.length > 0) {
				let dialog = new frappe.ui.Dialog({
					title: 'Item Details',
					fields: fields,
					primary_action_label: 'Submit',
					primary_action(values) {
						frappe.call({
							method: "metactical.metactical.page.packing_page_v3.packing_page_v3.set_item_values",
							args: {
								item: cur_item.item_code,
								values: values
							},
							callback: function(r) {
								if (r.message) {
									if(values.item_weight && values.item_weight > 0){
										cur_item.net_weight = values.item_weight;
									}
									pack_item(cur_item, barcode, amount);
								} else {
									frappe.msgprint("Error updating values");
								}
							}
						});
						
						this.hide();
					}
				});

				dialog.show();
			} else {
				pack_item(cur_item, barcode, amount);
			}


			//If picked item has no weight, then add weight first
			/*if(cur_item.net_weight == 0){
				frappe.prompt({
					fieldname: "item_weight",
					fieldtype: "Float",
					label: "Item Weight"
				}, 
				function(values){
					frappe.call({
						method: "metactical.metactical.page.packing_page_v3.packing_page_v3.set_item_weight",
						args: {
							item: cur_item.item_code,
							weight: values.item_weight
						},
						freeze: true,
						callback: function(ret){
							if(ret.message == "OK"){
								pack_item(cur_item, barcode, amount);
							}
						}
					});
				});
			}
			else{
				pack_item(cur_item, barcode, amount);
			}*/
			
			//return;
			throw "Break";
		}
	});
	
	frappe.utils.play_sound("error");
	frappe.msgprint("Wrong Barcode");
};

function pack_item(cur_item, barcode, amount=1){
	let packed_items = metactical.packing_page.packed_items;
	cur_item.qty -= amount;
	let cur_packed_item = packed_items.filter(
		(item) => item.item_code == cur_item.item_code
	);

	if (cur_packed_item.length > 0) {
		cur_packed_item[0].qty += amount;
	} else {
		cur_packed_item = $.extend(true, {}, cur_item);
		cur_packed_item.qty = amount;
		cur_packed_item.item_barcode = barcode;
		packed_items.push(cur_packed_item);
	}
	
	if (cur_item.qty == 0) {
		re_generate_current_item();
	}
	else{
		re_generate_current_item(cur_item);
	}

	populate_dom();
	$(".pack-items-btn").removeClass("d-none")
}
