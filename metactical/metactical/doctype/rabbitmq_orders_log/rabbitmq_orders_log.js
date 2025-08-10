// Copyright (c) 2025, Techlift Technologies and contributors
// For license information, please see license.txt

frappe.ui.form.on('RabbitMQ Orders Log', {
	refresh: function(frm) {
		frm.add_custom_button(__('Re-Sync Order'), function() {
			frappe.call({
				method: 'metactical.metactical.doctype.rabbitmq_orders_log.rabbitmq_orders_log.re_sync_order',
				args: {
					order_id: frm.doc.name
				},
				freeze: true,
				freeze_message: __('Re-syncing order...'),
				callback: function(r) {
					frappe.msgprint(__('Order re-synced successfully.'));
				}
			});
		})


		if (frm.doc.sales_order) {
			frm.add_custom_button(__('View Sales Order'), function() {
				frappe.set_route('Form', 'Sales Order', frm.doc.sales_order);
			});
		}
	}
});
