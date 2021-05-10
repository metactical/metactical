// Copyright (c) 2016, Techlift Technologies and contributors
// For license information, please see license.txt
/* eslint-disable */

var aday = new Date();
var to_date = aday.toISOString().split('T')[0];
aday.setDate(aday.getDate() - 7);
var from_date = aday.toISOString().split('T')[0];
var cur_report = null;
frappe.query_reports["Payments Status"] = {
	"filters": [
		{
            "fieldname":"from_date",
            "label": __("From Date"),
            "fieldtype": "Date",
            "default": from_date
        },
        {
            "fieldname":"to_date",
            "label": __("To Date"),
            "fieldtype": "Date",
            "default": to_date
        },
        {
            "fieldname":"source",
            "label": __("Source of Website"),
            "fieldtype": "Link",
            "options": "Lead Source"
        }
	],
	
	onload: function(report){
		cur_report = report;
	}
};

function add_notes(docname){
	console.log(cur_report);
	//frappe.set_route('query-report', 'Balance Sheet', {company: "Kangaroo Insurance"});
	var me = this
	var dialog = new frappe.ui.Dialog({
			title: __('Add Notes'),
			fields: [
				{fieldtype: 'Data', fieldname: 'notes', label:__("Notes"), reqd:true},
				{fieldtype: 'Link', read_only: 1, fieldname: 'sales_order', label:__("Sales Order"), options: 'Sales Order'}
			],
			primary_action: function() { 
				frappe.call({
					"method": "metactical.metactical.report.payments_status.payments_status.insert_notes",
					"args": dialog.get_values(),
					"callback": function(){
						dialog.hide();
						cur_report.refresh()
					}
				})
			},
			primary_action_label: __("Add")
		});
	dialog.set_value("sales_order", docname);
	dialog.show();
}
