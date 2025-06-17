// Copyright (c) 2021, Techlift Technologies and contributors
// For license information, please see license.txt

frappe.ui.form.on('Shipstation Settings', {
	refresh: function(frm) {
		frm.events.show_hide_fields(frm);

		// Add custom button to fetch stores
		if (!frm.is_new()) {
			frm.add_custom_button(__('View Shipstation Stores'), function() {
				frm.events.show_stores_dialog(frm);
			});
		}
	},
	
	shipping_charges_specified: function(frm) {
		frm.events.show_hide_fields(frm);
	},
	
	show_hide_fields: function(frm) {
		if(frm.doc.shipping_charges_specified){
			var charges_specified = frm.doc.shipping_charges_specified;
			frm.toggle_display('shipping_item', charges_specified=="In Item Table");
			frm.toggle_display('shipping_charge', charges_specified=="In Charges Table");
		}
	},

	show_stores_dialog: function(frm) {
		frappe.call({
			method: 'metactical.api.shipstation.get_shipstation_stores',
			args: {
				settingid: frm.doc.name
			},
			freeze: true,
			freeze_message: "Please wait while we fetch your Shipstation stores...",
			callback: function(r) {
				console.log("Ret: ", r);
				
				if (r.exc) {
					// Show error message if there's an exception
					frappe.msgprint({
						title: __('Error'),
						indicator: 'red',
						message: __('Failed to fetch stores from Shipstation.')
					});
					return;
				}
				
				const stores = r.message || [];
				
				// Create a dialog to display the stores
				const d = new frappe.ui.Dialog({
					title: __('Shipstation Stores'),
					fields: [
						{
							fieldtype: 'HTML',
							fieldname: 'stores_html'
						}
					],
					size: 'large',
					primary_action_label: __('Close'),
					primary_action: function() {
						d.hide();
					}
				});
				
				// Generate HTML table for the stores
				let html = '<div class="stores-container">';
				
				if (stores.length === 0) {
					html += '<div class="text-muted">No stores found</div>';
				} else {
					html += `
						<table class="table table-bordered">
							<thead>
								<tr>
									<th>${__('Store ID')}</th>
									<th>${__('Store Name')}</th>
									<th>${__('Marketplace')}</th>
									<th>${__('Source')}</th>
								</tr>
							</thead>
							<tbody>
					`;
					
					stores.forEach(store => {
						html += `
							<tr>
								<td>${store.store_id || ''}</td>
								<td>${store.store_name || ''}</td>
								<td>${store.marketplace_name || ''}</td>
								<td>${store.source || '<span class="text-muted">Not mapped</span>'}</td>
							</tr>
						`;
					});
					
					html += `
							</tbody>
						</table>
					`;
				}
				
				html += '</div>';
				
				// Set the HTML content and show the dialog
				d.fields_dict.stores_html.$wrapper.html(html);
				d.show();
			}
		});
	}
});
