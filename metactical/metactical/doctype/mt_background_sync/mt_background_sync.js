// Copyright (c) 2025, Techlift Technologies and contributors
// For license information, please see license.txt
var filter_group = null;

frappe.ui.form.on('MT Background Sync', {
	refresh: function(frm) {
		// if (!frm.doc.pid){
			frm.add_custom_button(__('Start Sync'), function() {
				frappe.call({
					method: "metactical.metactical.doctype.mt_background_sync.mt_background_sync.start_sync",
					args: {
						name: frm.doc.name,
						filters: frm.events.get_filters(filter_group)
					},
					freeze: true,
					freeze_message: __("Initiating Background Sync ..."),
					callback: function(r) {
						frappe.msgprint(r.message)
						frm.reload_doc();
					}
				});
			})
		// }else{
			frm.add_custom_button(__('Stop Sync'), function() {
				frappe.call({
					method: "metactical.metactical.doctype.mt_background_sync.mt_background_sync.stop_sync",
					args: {
						name: frm.doc.name
					},
					freeze: true,
					freeze_message: __("Stopping Background Sync ..."),
					callback: function(r) {
						frappe.msgprint(r.message)
						frm.reload_doc();
					}
				});
			})
		// }
	},
	setup: function(frm) {
		frappe.db.count("Item").then((count) => {
			frm.get_field("filters_detail").$wrapper.html(
				`<p><b>${__("Total Items:")}  ${count}</b></p>`)
		});

		frappe.model.with_doctype("Item", () => {
			filter_group = new frappe.ui.FilterGroup({
				parent: frm.get_field("filter_area").$wrapper,
				doctype: "Item",
				on_change: () => {
					var total = frappe.db.count("Item", {
						filters: frm.events.get_filters(filter_group)
					})
					
					total.then((total) => {
						frm.get_field("filters_detail").$wrapper.html(
							`<p><b>${__("Total Items:")}  ${total}</b></p>`
						);
					});
				},
			});
		});

	},

	get_filters(filter_group) {
		return filter_group.get_filters().map((filter) => {
			return filter.slice(0, 4);
		});
	}
});
