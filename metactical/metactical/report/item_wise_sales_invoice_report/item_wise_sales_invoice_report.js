var aday = new Date();
var to_date = aday.toISOString().split('T')[0];
aday.setDate(aday.getDate() - 7);
var from_date = aday.toISOString().split('T')[0];
var cur_report = null;

frappe.query_reports["Item-Wise Sales Invoice Report"] = {
	"filters": [
		{
			"fieldname":"from_date",
			"label": __("From Date"),
			"fieldtype": "Date",
			"default": from_date,
			"width": "80"
		},
		{
			"fieldname":"to_date",
			"label": __("To Date"),
			"fieldtype": "Date",
			"default": to_date
		},
	]
}
