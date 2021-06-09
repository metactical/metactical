frappe.query_reports["Sales Report RASUSA - Full V1"] = {
	"filters": [
		{
			"fieldname":"supplier",
			"label": __("Supplier"),
			"fieldtype": "MultiSelectList",
			"options": "Supplier",
			get_data: function(txt) {
				return frappe.db.get_link_options("Supplier", txt);
			},
		},
		{
			"fieldname":"limit",
			"label": __("Limit"),
			"fieldtype": "Select",
			"options": ["20", "500", "1000", "5000", "10000", "All"],
			"default": 20
		},
	]
};
