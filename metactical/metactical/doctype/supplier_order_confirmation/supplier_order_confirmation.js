frappe.ui.form.on('Supplier Order Confirmation', {
	refresh: function(frm) {
		if (frm.doc.docstatus !== 1) {
			return;
		}

		var has_unreceived = (frm.doc.items || []).some(function(d) {
			return !d.received_flag
				&& flt(d.confirmed_qty) > 0
				&& !['Out of Stock', 'Discontinued'].includes(d.line_status);
		});

		if (!has_unreceived) {
			return;
		}

		frm.add_custom_button(__('Purchase Receipt'), function() {
			frappe.call({
				method: 'metactical.custom_scripts.purchase_order.purchase_receipt_from_source.make_purchase_receipt_from_confirmation',
				args: { soc_name: frm.doc.name },
				freeze: true,
				callback: function(r) {
					if (r.message) {
						var doc = frappe.model.sync(r.message)[0];
						frappe.set_route('Form', doc.doctype, doc.name);
					}
				}
			});
		}, __('Create'));
	}
});
