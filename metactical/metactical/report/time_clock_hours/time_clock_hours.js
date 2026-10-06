frappe.query_reports["Time Clock Hours"] = {
	filters: [
		{ fieldname: "from_date", label: __("From (work day)"), fieldtype: "Date", reqd: 1, default: frappe.datetime.add_days(frappe.datetime.get_today(), -14) },
		{ fieldname: "to_date", label: __("To (work day)"), fieldtype: "Date", reqd: 1, default: frappe.datetime.get_today() },
		{ fieldname: "country", label: __("Country"), fieldtype: "Select", options: "\nCA\nUS\nOTHER\nUNKNOWN" },
		{ fieldname: "employee", label: __("Employee"), fieldtype: "Link", options: "Employee" },
		{ fieldname: "show_work_zone", label: __("Also show times in the employee's work zone"), fieldtype: "Check", default: 1 },
	],
};
