// Copyright (c) 2024, Techlift Technologies and contributors
// For license information, please see license.txt

frappe.provide("metactical.SalesOrdersFromExcel");

metactical.SalesOrdersFromExcel = erpnext.TransactionController.extend({
	setup: function() {

	},
	onload: function(){

	},
	refresh: function(frm) {
		if (frm.doc.docstatus == 0)
		{
			frm.add_custom_button(__('Submit'), function() {
				frappe.call({
					method: "metactical.custom_scripts.sales_orders_from_excel.sales_orders_from_excel.submit_sales_order_from_excel",
					args: {
						"doc": frm.doc.name
					},
				})
			});
		}
	},
	currency: function() {
		let transaction_date = this.frm.doc.transaction_date || this.frm.doc.posting_date;

		let me = this;
		this.set_dynamic_labels();
		let company_currency = this.get_company_currency();
		// Added `ignore_price_list` to determine if document is loading after mapping from another doc
		if(this.frm.doc.currency && this.frm.doc.currency !== company_currency
				&& !(this.frm.doc.__onload && this.frm.doc.__onload.ignore_price_list)) {

			this.get_exchange_rate(transaction_date, this.frm.doc.currency, company_currency,
				function(exchange_rate) {
					if(exchange_rate != me.frm.doc.conversion_rate) {
						me.set_margin_amount_based_on_currency(exchange_rate);
						me.set_actual_charges_based_on_currency(exchange_rate);
						me.frm.set_value("conversion_rate", exchange_rate);
					}
				});
		} else {
			// company currency and doc currency is same
			// this will prevent unnecessary conversion rate triggers
			if(this.frm.doc.currency === this.get_company_currency()) {
				this.frm.set_value("conversion_rate", 1.0);
			} else {
				this.conversion_rate();
			}
		}
	},

	selling_price_list: function() {
		this.apply_price_list();
		this.set_dynamic_labels();
	},

	taxes_and_charges: function() {
		// Replacing the default function with
	},
});

frappe.ui.form.on('Sales Orders From Excel', {
	setup: function(frm) {
		frm.set_query('company_address', function(doc) {
			if(!doc.company) {
				frappe.throw(__('Please set Company'));
			}

			return {
				query: 'frappe.contacts.doctype.address.address.address_query',
				filters: {
					link_doctype: 'Company',
					link_name: doc.company
				}
			};
		});
	},

	company_address: function() {
		var me = this;
		if(this.frm.doc.company_address) {
			frappe.call({
				method: "frappe.contacts.doctype.address.address.get_address_display",
				args: {"address_dict": this.frm.doc.company_address },
				callback: function(r) {
					if(r.message) {
						me.frm.set_value("company_address_display", r.message)
					}
				}
			})
		} else {
			this.frm.set_value("company_address_display", "");
		}
	},



});

$.extend(cur_frm.cscript, new metactical.SalesOrdersFromExcel({frm: cur_frm}));