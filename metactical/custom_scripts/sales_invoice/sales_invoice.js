frappe.ui.form.on('Sales Invoice', {
	refresh: function(frm){
		if (frm.doc.__islocal)
			frm.set_value("neb_payment_completed_at", null)

		frm.trigger("update_custom_buttons")

		//frm.add_custom_button(__('Journal Entry'), () => frm.events.create_journal_entry(frm), __("Create"));
	},
	validate: function(frm){
		if (frm.doc.neb_pay_with_store_credit && !frm.doc.advances.length){
			frappe.msgprint(__("Please select advances to pay with store credit."));
			frm.trigger("customer");
			frappe.validated = false;
		}
	},
	neb_pay_with_store_credit: function(frm){
		if (frm.doc.neb_pay_with_store_credit){
			if (!frm.doc.customer){
				frm.set_value("neb_pay_with_store_credit", 0);
				frappe.msgprint(__("Please select a customer first."));
				return;
			}

			frm.trigger('get_store_credit_account');	
		}
		else{
			frm.trigger("customer");
			frm.set_value("advances", []);
		}
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

	customer: function(frm){
		if (frm.doc.neb_pay_with_store_credit){
			frm.trigger('get_store_credit_account');
		}
	},
	currency: function(frm){
		if (frm.doc.neb_pay_with_store_credit){
			frm.trigger('get_store_credit_account');
		}
	},

	get_store_credit_account: function(frm){
		frappe.call({
			method: "metactical.custom_scripts.sales_invoice.sales_invoice.get_store_credit_account",
			args: {
				"currency": frm.doc.currency
			},
			callback: function(r){
				if(r.message){
					if (r.message != frm.doc.debit_to){
						frm.set_value("debit_to", r.message);
						frm.trigger("get_advances")
					}
				}
			}
		});
	},

	debit_to: function(frm){
		if (frm.doc.neb_pay_with_store_credit){
			// if debit does not starts with "Store Credit" then set it to store credit
			if (!frm.doc.debit_to.startsWith("Store Credit")){
				frm.trigger("get_store_credit_account");
			}
		}
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
