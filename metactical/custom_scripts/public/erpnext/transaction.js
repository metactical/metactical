erpnext.TransactionController = class TransactionController extends erpnext.TransactionController{
	// Metactical Customization: Add scan to confirm button functionality
	ais_scan_to_confirm() {
		var me = this;
		var items = this.frm.doc.items;
		if(this.frm.doc.items && this.frm.doc.items.length > 0){
			var fields = [
				{'fieldtype': 'Link', 'label': 'Item', 'options': 'Item', 'fieldname': 'item_code', 'in_list_view': 1},
				{'fieldtype': 'Float', 'label': 'Qty', 'fieldname': 'qty', 'in_list_view': 1}
			]
			var scanned_dialog = new frappe.ui.Dialog({
				'fields': [
					{'fieldtype': 'Data', 'fieldname': 'barcode', 'label': 'Scan Barcode'},
					{'fieldtype': 'Table', 'fieldname': 'items', 'fields': fields, 'data': []}
				],
				'primary_action': function(){
					var values = scanned_dialog.get_values('items');
					for(let i in values.items){
						var row = values.items[i];
						let exists = items.filter((itm) => itm.item_code == row.item_code);
						if(exists.length > 0){
							exists[0].qty = row.qty;
						}
					}
					scanned_dialog.hide();
					me.frm.refresh_field('items');
				},
				'secondary_action': function(){
					scanned_dialog.hide();
				},
				'secondary_action_label': 'Cancel',
				'no_submit_on_enter': true
			});
			
			scanned_dialog.barcode_scanned = function(){
				if(scanned_dialog.get_values()['barcode'] == '' || scanned_dialog.get_values()['barcode'] == null){
					return
				}
				frappe.call({
					method: "erpnext.selling.page.point_of_sale.point_of_sale.search_for_serial_or_batch_or_barcode_number",
					args: {
						search_value: scanned_dialog.get_values()['barcode']
					}
				}).then(r => {
					const data = r && r.message;
					if (!data || Object.keys(data).length === 0) {
						frappe.utils.play_sound("error");
						frappe.show_alert({
							message: __("Wrong barcode"),
							indicator: 'orange'
						});
					}
					else{
						let existing_item = items.filter((itm) => itm.item_code == data.item_code);
						if(existing_item.length > 0){
							var dialog_data = scanned_dialog.fields_dict.items.grid.data;
							let existing_row = dialog_data.filter((row) => row.item_code == data.item_code)
							if(existing_row.length > 0){
								existing_row[0].qty = existing_row[0].qty + 1
							}
							else{
								dialog_data.push({"item_code": data.item_code, "qty": 1})
							}
							scanned_dialog.fields_dict.items.grid.refresh();
							scanned_dialog.fields_dict.barcode.set_value('');
							frappe.utils.play_sound("alert");
						}
						else{
							frappe.utils.play_sound("error");
							frappe.show_alert({
								message: __("Item not in list"),
								indicator: 'orange'
							});
						}
					}
				});
			}
						
			scanned_dialog.fields_dict.barcode.input.onkeypress = function(event){
				if(event.keyCode == 13)
				{
					scanned_dialog.barcode_scanned();
				}
			};
			scanned_dialog.show();
		}
	}
};
