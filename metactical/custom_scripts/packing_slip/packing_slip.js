frappe.ui.form.on("Packing Slip", {
	delivery_note(frm, cdt, cdn) {
		if (frm.doc.delivery_note) {
			cur_frm.cscript.get_items(frm, cdt, cdn)
		}
	},
	
	scan_item_barcode(frm) {
		if (frm.doc.scan_item_barcode) {
			frm.set_value('item_barcode', frm.doc.scan_item_barcode)
			frappe.call('sales_report_full.api.packing_slip.fetch_item', {
					barcode: frm.doc.scan_item_barcode
				})
				.then(r => {
					if (r.message) {
						let items = frm.doc.items;
						for (let i in items) {
							if (items[i].item_code == r.message) {
								const new_qty = items[i].scanned_qty + 1;
								let row = items[i];
								frappe.model.set_value(row.doctype, row.name, 'scanned_qty', new_qty)
							}
						}
						frm.refresh_field('items')
					} else {
						frappe.msgprint('No match found');
					}
				})
		}
		frm.set_value('scan_item_barcode', null);
		cur_frm.scroll_to_field('scan_item_barcode');
	}
});
