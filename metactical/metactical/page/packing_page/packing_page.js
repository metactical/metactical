frappe.provide("havenir.packing_slip");

frappe.pages["packing-page"].on_page_load = function (wrapper) {
	// Check if user has permisssion to add
	frappe.call({
		method: "metactical.metactical.page.packing_page.packing_page.check_to_add_permission",
		freeze: true,
		callback: function(ret){
			havenir.packing_slip.has_add_permission = ret.message;
		}
	});
	
	//Load the default warehouse
	havenir.packing_slip.default_warehouse = "";
	frappe.call({
		method: "metactical.metactical.page.packing_page.packing_page.get_default_warehouse",
		freeze: true,
		callback: function(ret){
			havenir.packing_slip.default_warehouse = ret.message;
			frappe.packing_slip = new PackingPage(wrapper);
		}
	});
};

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
			title: "Packing Slip",
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
			frappe.render_template("packing_page", {
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
					havenir.packing_slip.fetch_dn_items();
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
						havenir.packing_slip.calc_packing_items(value);
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
				fieldtype: "Link",
				options: "Picklist Tote",
				get_query: function(){
					return {
						filters: [
							["warehouse", "=", selected_warehouse.get_value()],
							["current_delivery_note", "is", "set"]
						]
					}
				},
				change: function(){
					frappe.call({
						method: "metactical.metactical.page.packing_page.packing_page.get_delivery_from_tote",
						args: {
							tote: tote_barcode_field.get_value()
						},
						freeze: true,
						callback: function(ret){
							delivery_note_field.set_value(ret.message);
						}
					});
				}
			},
			render_input:true
		});
		
		// Load default warehouse
		if(havenir.packing_slip.default_warehouse != ""){
			$('[data-fieldname=selected_warehouse]').val(havenir.packing_slip.default_warehouse);
			$('.picklist-tote-wrapper').show();
		}
	}
}


function create_new() {
	$('input[data-fieldname="tote_barcode"]').val("");
	$('input[data-fieldname="delivery_note"]').val("");
	havenir.packing_slip.fetch_dn_items(true);
}

function refresh() {
	$('input[data-fieldname="tote_barcode"]').val("");
	$('input[data-fieldname="delivery_note"]').val("");
	havenir.packing_slip.fetch_dn_items(true);
}

function save_form() {
	let packed_items = havenir.packing_slip.packed_items;
	let cur_doc = havenir.packing_slip.cur_doc;
	cur_doc.items = packed_items;

	frappe.call({
		method: "frappe.desk.form.save.savedocs",
		args: {
			doc: cur_doc,
			action: "Submit"
		},
		freeze: true,
		btn: $(".primary-action"),
		callback: (r) => {
			refresh();
		},
		error: (r) => {
			console.error(r);
		},
	});
}

function count_pending_items() {
	const items = havenir.packing_slip.pending_items;
	let count = 0;
	for (const item of items) {
		count += item.qty;
	}

	$(".pending-items-count").html(count + " Item(s) left");
}

function count_packed_items() {
	const items = havenir.packing_slip.packed_items;
	let count = 0;
	for (const item of items) {
		count += item.qty;
	}

	$(".packed-items-count").html(count + " Item(s) Packed");
}

function populate_pending_items() {
	const items = havenir.packing_slip.pending_items;
	let items_template = "";
	if (items.length > 0) {
		items_template = frappe.render_template("pending_items", {
			items: items,
		});
	}

	$(".pending-items-wrap").html(items_template);
}

function populate_current_item() {
	const item = havenir.packing_slip.current_item;
	if (item.item_code) {
		let add_button_html = "Scan this item to move next "
		if(havenir.packing_slip.has_add_permission){
			add_button_html += "or <button class='btn btn-default btn-sm' onClick='addOneItem()'>Click to Add</button> \
				<button class='btn btn-default btn-sm' onClick='addMultiple()'>Add Multiple</button>";
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

function populate_packed_items() {
	const items = havenir.packing_slip.packed_items;
	let pending_items = havenir.packing_slip.pending_items;
	let items_template = "";
	
	if(items.length > 0){
		items_template = frappe.render_template("packing_items", {
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
		if(pending_items.length == 0 && !havenir.packing_slip.confirm_raised){
			havenir.packing_slip.confirm_raised = true;
			frappe.confirm(
				'Submit packing slip?',
				function(){
					havenir.packing_slip.confirm_raised = false;
					save_form();
				},
				function(){
					havenir.packing_slip.confirm_raised = false;
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
	pending_items = havenir.packing_slip.pending_items;
	current_item = havenir.packing_slip.current_item;
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
					havenir.packing_slip.item_clicked = true;
					havenir.packing_slip.current_item = row;
				}
			});
		} else {
			havenir.packing_slip.current_item = pending_items[0];
		}
	} else {
		havenir.packing_slip.current_item = {};
	}
	populate_dom();
	return;
}

function populate_dom() {
	count_pending_items();
	count_packed_items();
	populate_pending_items();
	populate_current_item();
	populate_packed_items();
}

function addOneItem() {
	let cur_item = havenir.packing_slip.current_item;
	if (cur_item.item_code && cur_item.item_barcode) {
		havenir.packing_slip.item_clicked = true;
		havenir.packing_slip.calc_packing_items(cur_item.item_barcode[0]);
	} else {
		frappe.show_alert({
			message: "Barcode not found",
			indicator: "red",
		});
	}
}

function addMultiple(){
	let cur_item = havenir.packing_slip.current_item;
	frappe.prompt(
		[{"fieldtype": "Int", "fieldname": "amount", "label": "Number of Items to Add", "reqd": 1}],
		function(values){
			if(values.amount > cur_item.qty){
				frappe.throw("You can only add a maximum of " + cur_item.qty + " items");
			}
			else{
				havenir.packing_slip.item_clicked = true;
				havenir.packing_slip.calc_packing_items(cur_item.item_barcode[0], values.amount);
			}
		}
	);
}

function selectItem(item) {
	re_generate_current_item(item);
}

havenir.packing_slip.fetch_dn_items = (from_refresh = false) => {
	let delivery_note = $('input[data-fieldname="delivery_note"]').val();

	if (!delivery_note) {
		let template = frappe.render_template("packing_page", {
			no_data_feedback: "Select Delivery Note",
			delivery_note: 0,
		});

		$(".packing-slip-wrapper").html(template);

		havenir.packing_slip.pending_items = [];
		havenir.packing_slip.current_item = {};
		havenir.packing_slip.packed_items = [];
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
				havenir.packing_slip.cur_doc = r.docs[0];

				if (!items.length) {
					no_data_feedback = "No items for this Delivery Note";
					$(".packing-slip-wrapper").html(
						frappe.render_template("packing_page", {
							no_data_feedback: no_data_feedback,
							delivery_note: 0,
						})
					);
				} else {
					frappe
						.call("metactical.api.packing_slip.get_item_master", {
							items: items,
						})
						.then((r) => {
							items = r.message;

							$(".packing-slip-wrapper").html(
								frappe.render_template("packing_page", {
									no_data_feedback: 0,
									delivery_note: delivery_note,
								})
							);

							if (havenir.packing_slip.item_clicked && !from_refresh) {
								//A hack to fix a bug(?) when the delivery note loaded. First click anywhere 
								//on the page calls refresh()
								havenir.packing_slip.item_clicked = false;
							} else {
								havenir.packing_slip.pending_items = items;
								havenir.packing_slip.current_item = items[0];
								havenir.packing_slip.packed_items = [];
							}

							populate_dom();
						});
				}
			},
		});
	}
};

havenir.packing_slip.calc_packing_items = (barcode, amount=1) => {
	let packed_items = havenir.packing_slip.packed_items;
	//let cur_item = havenir.packing_slip.current_item;
	let pending_items = havenir.packing_slip.pending_items;

	if (barcode == "SKIP") {
		re_generate_current_item();
		return;
	}
	
	pending_items.forEach(function(cur_item){
		if (cur_item.item_barcode.indexOf(barcode) != -1) {
			havenir.packing_slip.current_item = cur_item;
			if(amount > cur_item.qty){
				frappe.throw("You can only add a maximum of " + cur_item.qty + " items");
			}
			frappe.utils.play_sound("alert");
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
			//return;
			throw "Break";
		}
	});
	
	frappe.utils.play_sound("error");
	frappe.msgprint("Wrong Barcode");
	/*frappe.show_alert({
		message: __("Wrong Barcode"),
		indicator: "red"
	});*/
	
};
