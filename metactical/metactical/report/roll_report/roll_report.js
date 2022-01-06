// Copyright (c) 2016, Techlift Technologies and contributors
// For license information, please see license.txt
/* eslint-disable */

var today = new Date();
default_cycle = ''
frappe.call({
	"method": "metactical.metactical.report.roll_report.roll_report.get_current_cycle",
	"freeze": true,
	"callback": function(ret){
		if(ret.message){
			default_cycle = ret.message;
			frappe.query_reports["Roll Report"] = {
				"filters": [
					{
						"fieldtype": "Link",
						"fieldname": "year",
						"options": "Fiscal Year",
						"label": "Year",
						"reqd": 1,
						"default": today.getFullYear()
					},
					{
						"fieldtype": "Link",
						"fieldname": "payment_cycle",
						"options": "Payment Cycle",
						"label": "Payment Cycle",
						"reqd": 1,
						"default": default_cycle,
						"get_query": function(){ 
							var year = frappe.query_report.get_filter_value('year');
							return {'filters': [['year','=', year]]}
						}
					}
				]
			};
		}
	}
});

