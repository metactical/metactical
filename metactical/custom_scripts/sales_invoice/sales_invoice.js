frappe.ui.form.on('Sales Invoice', {
	refresh: function(frm){
		if (frm.doc.__islocal)
			frm.set_value("neb_payment_completed_at", null)

		frm.trigger("update_custom_buttons")

		//frm.add_custom_button(__('Journal Entry'), () => frm.events.create_journal_entry(frm), __("Create"));
	},
	update_custom_buttons: function(frm){
		var seconds = 0;
		var interval = setInterval(() => {
			var custom_buttons = Object.keys(frm.custom_buttons)

			if (custom_buttons.length){
				clearInterval(interval);
				if ("Payment Request" in cur_frm.custom_buttons){
					frm.remove_custom_button("Payment Request", 'Create');
					frm.add_custom_button("USAePay Payment Request", () => frm.events.create_usaepay_payment_request(frm), __("Create"));		
				}
			}
			else if (seconds > 5){
				clearInterval(interval);
			}
			seconds++;
		}, 1000);
	},
	create_usaepay_payment_request: function(frm){
		const payment_request_type = "Inward"
		frappe.call({
			method:"metactical.custom_scripts.payment_request.payment_request.make_payment_request",
			args: {
				dt: frm.doc.doctype,
				dn: frm.doc.name,
				recipient_id: frm.doc.contact_email,
				payment_request_type: payment_request_type,
				party_type: "Customer",
				party: frm.doc.customer
			},
			callback: function(r) {
				if(!r.exc){
					var doc = frappe.model.sync(r.message);
					frappe.set_route("Form", r.message.doctype, r.message.name);
				}
			}
		})
	},
	create_journal_entry(frm){
		var d = new frappe.ui.Dialog({
			'fields': [
				{
					"fieldtype": "Select",
					"fieldname": "purpose",
					"options": "Create Credit Note and Refund Customer\nRefund Advance Payment",
					"reqd": 1,
					"label": __('Purpose')
				},
				{
					"fieldtype": "Link",
					"options": "Account",
					"reqd": 1,
					"fieldname": "bank_cash",
					"label": __("Bank/Cash Account"),
					"get_query": function () {
						return {
							filters: [
								{"account_type": ["in", ["Bank", "Cash"]]},
								{"is_group": 0}
							]
						}
					}
				},
				{
					"fieldtype": "Currency",
					"fieldname": "credit_amount",
					"reqd": 1,
					"label": __("Credit Amount"),
					"onchange": function(e){
						console.log(e);
					}
				}
			],
			primary_action: function(){
				var values = d.get_values();
				return frappe.call({
					type: "GET",
					method: "metactical.custom_scripts.sales_invoice.sales_invoice.create_journal_entry",
					args: {
						"source_name": cur_frm.docname,
						"bank_cash": values.bank_cash,
						"amount": values.credit_amount,
						"purpose": values.purpose
					},
					freeze: true,
					callback: function(r) {
						console.log(r);
						if(!r.exc) {
							var doc = frappe.model.sync(r.message);
							frappe.set_route("Form", r.message.doctype, r.message.name);
						}
					}
				});
			}
		});
		d.show();
		console.log(d);
	}
});
