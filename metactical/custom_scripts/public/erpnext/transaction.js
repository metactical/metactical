erpnext.TransactionController = erpnext.TransactionController.extend({
	scan_barcode: function() {
		let me = this;

		if(this.frm.doc.scan_barcode) {
			frappe.call({
				method: "erpnext.selling.page.point_of_sale.point_of_sale.search_for_serial_or_batch_or_barcode_number",
				args: {
					search_value: this.frm.doc.scan_barcode
				}
			}).then(r => {
				const data = r && r.message;
				if (!data || Object.keys(data).length === 0) {
					frappe.utils.play_sound("error");
					frappe.show_alert({
						message: __('Cannot find Item with this Barcode'),
						indicator: 'red'
					});
					return;
				}
				else{
					frappe.utils.play_sound("alert");
				}

				me.modify_table_after_scan(data);
			});
		}
		return false;
	}
});
