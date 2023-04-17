frappe.ui.form.on('Payment Entry', {
	source_exchange_rate: function(frm) {
		if (frm.doc.paid_amount) {
			frm.set_value("base_paid_amount", flt(frm.doc.paid_amount) * flt(frm.doc.source_exchange_rate));
			// target exchange rate should always be same as source if both account currencies are same
			if(frm.doc.paid_from_account_currency == frm.doc.paid_to_account_currency) {
				frm.set_value("target_exchange_rate", frm.doc.source_exchange_rate);
				frm.set_value("base_received_amount", frm.doc.base_paid_amount);
			}

			frm.events.set_unallocated_amount(frm);
		}

		// Make read only if Accounts Settings doesn't allow stale rates
		frm.set_df_property("source_exchange_rate", "read_only", erpnext.stale_rate_allowed() ? 0 : 1);
		
		if(frm.doc.received_amount){
			frm.set_value('paid_amount', frm.doc.received_amount / frm.doc.source_exchange_rate);
		}
	}
});
