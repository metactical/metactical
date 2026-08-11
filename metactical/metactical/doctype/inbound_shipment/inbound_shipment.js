frappe.ui.form.on('Inbound Shipment', {
	refresh: function(frm) {
		if (frm.doc.docstatus !== 1) {
			return;
		}

		var has_unreceived = (frm.doc.items || []).some(function(d) {
			return !d.received_flag && flt(d.shipped_qty) > 0;
		});

		if (!has_unreceived) {
			return;
		}

		frm.add_custom_button(__('Purchase Receipt (Whole Shipment)'), function() {
			create_pr_from_shipment(frm);
		}, __('Create'));

		var open_boxes = (frm.doc.boxes || []).filter(function(b) { return !b.received; });
		if (open_boxes.length) {
			frm.add_custom_button(__('Purchase Receipt (Select Box)'), function() {
				prompt_box_and_create_pr(frm, open_boxes);
			}, __('Create'));
		}
	}
});

function create_pr_from_shipment(frm, box_no) {
	frappe.call({
		method: 'metactical.custom_scripts.purchase_order.purchase_receipt_from_source.make_purchase_receipt_from_shipment',
		args: { ins_name: frm.doc.name, box_no: box_no || null },
		freeze: true,
		callback: function(r) {
			if (r.message) {
				var doc = frappe.model.sync(r.message)[0];
				frappe.set_route('Form', doc.doctype, doc.name);
			}
		}
	});
}

function prompt_box_and_create_pr(frm, open_boxes) {
	frappe.prompt(
		[{
			fieldname: 'box_no',
			label: __('Box No'),
			fieldtype: 'Select',
			options: open_boxes.map(function(b) { return b.box_no; }),
			reqd: 1
		}],
		function(values) {
			create_pr_from_shipment(frm, values.box_no);
		},
		__('Select Box'),
		__('Create')
	);
}
