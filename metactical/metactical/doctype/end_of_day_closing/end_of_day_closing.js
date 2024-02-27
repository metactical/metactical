// Copyright (c) 2024, Techlift Technologies and contributors
// For license information, please see license.txt

frappe.ui.form.on('End of Day Closing', {
	refresh: function(frm){
		console.log(frm);
		frm.events.load_cash_table(frm);
	},
	user: function(frm){
		frm.events.load_data(frm);
	},
	
	closing_date: function(frm){
		frm.events.load_data(frm);
	},
	
	pos_profile: function(frm){
		frm.events.load_data(frm);
	},
	
	cash_float: function(frm){
		frm.set_value("subtracted_float", -frm.doc.cash_float);
		frm.events.calculate_totals(frm);
	},
	
	load_cash_table: function(frm){
		if(!frm.doc.eod_cash || frm.doc.eod_cash.length == 0){
			var coins = [100, 50, 20, 10, 5, 2, 1, 0.25, 0.10, 0.05, 0.01];
			coins.forEach(function(coin){
				var row = frm.add_child("eod_cash");
				row.cash = coin;
				row.qty = 0;
				row.amount = 0;
			});
			frm.refresh_fields("eod_cash");
		}
		setTimeout(() => {
			frm.get_field("eod_cash").grid.cannot_add_rows = true;
			frm.refresh_field("eod_cash");
		}, 200);
	},
	
	load_data: function(frm) {
		if(frm.doc.user && frm.doc.closing_date && frm.doc.pos_profile) {
			frappe.call({
				method: "metactical.metactical.doctype.end_of_day_closing.end_of_day_closing.get_data",
				freeze: true,
				args: {
					"user": frm.doc.user,
					"pos_profile": frm.doc.pos_profile,
					"closing_date": frm.doc.closing_date,
					"source": frm.doc.lead_source
				},
				callback: function(ret){
					console.log({"ret": ret});
					if(Object.keys(ret.message.payments).length > 0){
						frm.set_value("eod_payments", []);
						for(var mop in ret.message.payments){
							var row = frm.add_child("eod_payments");
							row.mode_of_payment = mop;
							row.expected = ret.message.payments[mop];
							row.actual = 0;
							row.difference = ret.message.payments[mop];
						}
						frm.refresh_field("eod_payments");
					}
					
					if(ret.message.invoices.length > 0){
						frm.set_value("invoices", []);
						ret.message.invoices.forEach(function(invoice){
							var row = frm.add_child("invoices");
							row.type = invoice.reference_doctype
							row.invoice = invoice.reference_name;
							row.amount_paid = invoice.amount_paid;
							row.owing = invoice.owing;
						});
						frm.refresh_field("invoices");
					}
					frm.set_value("expected_cash", ret.message.expected_cash);
					frm.events.calculate_totals(frm);
				}
			});
		}
	},
	
	calculate_totals: function(frm){
		var cash_total = 0
		frm.doc.eod_cash.forEach(function(row){
			cash_total += row.amount;
		});
		
		// Round up or down to the nearest $5
		var cash_after_round = Math.floor(cash_total / 5) * 5;
		
		frm.set_value("total_cash", cash_total);
		frm.set_value("rounding", cash_after_round - cash_total);
		frm.set_value("total_cash_drop", cash_total - frm.doc.cash_float - (cash_total - cash_after_round));
		
		// Modes of payment
		var expected_total = 0;
		var actual_total = 0;
		frm.doc.eod_payments.forEach(function(row){
			expected_total += row.expected;
			actual_total += row.actual;
		});
		frm.set_value("mop_total_expected", expected_total);
		frm.set_value("mop_total_actual", actual_total);
		frm.set_value("mop_total_difference", expected_total - actual_total);
	}
});

frappe.ui.form.on("EOD Cash", {
	qty: function(frm, cdt, cdn){
		var row = locals[cdt][cdn];
		var to_add = {2: 50, 1: 25, 0.25: 10, 0.1: 5, 0.05: 2, 0.01: 0.5};
		var amount = row.cash * row.qty 
		if(row.cash <= 2){
			amount += (to_add[row.cash] * row.rolls);
		}
		frappe.model.set_value(cdt, cdn, "amount", amount);
		frm.events.calculate_totals(frm);
	},
	
	rolls: function(frm, cdt, cdn){
		var row = locals[cdt][cdn];
		var to_add = {2: 50, 1: 25, 0.25: 10, 0.1: 5, 0.05: 2, 0.01: 0.5};
		if(row.cash > 2){
			frappe.model.set_value(cdt, cdn, "rolls", 0);
			frappe.throw("Error: Rolls can only be added for coins of $2 or less.");
		}
		else{
			var amount = (row.cash * row.qty) + (to_add[row.cash] * row.rolls);
			frappe.model.set_value(cdt, cdn, "amount", amount);
			frm.events.calculate_totals(frm);
		}
	}
});

frappe.ui.form.on("EOD Payments", {
	actual: function(frm, cdt, cdn){
		var row = locals[cdt][cdn];
		var diff = row.expected - row.actual
		frappe.model.set_value(cdt, cdn, "difference", diff);
		frm.events.calculate_totals(frm);
	}
});
