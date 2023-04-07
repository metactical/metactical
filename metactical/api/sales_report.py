import frappe
import json

@frappe.whitelist(allow_guest=1)
def get_us_data(**args):
	filters = frappe._dict(args)
	data = {}
	where = "bin.warehouse = '01A-ActiveStock - CUS'"
	left_join = ""
	if filters.get("supplier") and filters.supplier != "":
		where += " AND supplier = '{}'".format(filters.get("supplier"))
		left_join += " LEFT JOIN `tabItem Supplier` AS supplier ON supplier.parent = item.name"
	
	items = frappe.db.sql("""
				SELECT 
					item.item_code, actual_qty-reserved_qty AS qty 
				FROM 
					`tabBin` AS bin
				LEFT JOIN
					`tabItem` AS item ON item.name = bin.item_code
				{left_join}
				WHERE 
					{where}
				""".format(left_join = left_join, where = where), as_dict=1)
	if len(items) > 0:
		for item in items:
			data[item.item_code] = item.qty
	return data
