import frappe

@frappe.whitelist(allow_guest=True)
def get_items(search_value=""):
	query = """
		SELECT
			bin.item_code, bin.actual_qty
		FROM 
			`tabBin` AS bin
		LEFT JOIN
			`tabItem` AS item ON item.item_code = bin.item_code
		LEFT JOIN
			`tabItem Barcode` AS barcode ON barcode.parent = item.name 
		WHERE
			bin.warehouse = '01A-ActiveStock - CUS' AND (barcode.barcode = "{search_text}" or 
			item.ifw_retailskusuffix like "{search_text}%") AND item.disabled = 0
			AND item.has_variants = 0 AND item.is_sales_item = 1
		GROUP BY
			bin.item_code, bin.actual_qty
		""".format(search_text=search_value)
	items_data = frappe.db.sql(query ,as_dict=1)
	return items_data
