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

@frappe.whitelist(allow_guest=True)
def get_total_items(search_text):
	query = f"""
		SELECT
			bin.item_code, item.item_name, SUM(bin.actual_qty) AS actual_qty,
			item.ifw_retailskusuffix AS retail_sku, item.ifw_location,
			GROUP_CONCAT(DISTINCT barcode.barcode SEPARATOR '<br>') AS barcode,
			item.variant_of AS template_sku
		FROM 
			`tabBin` AS bin
		LEFT JOIN
			`tabItem` AS item ON item.item_code = bin.item_code
		LEFT JOIN
			`tabItem Barcode` AS barcode ON barcode.parent = item.name 
		WHERE
			bin.warehouse LIKE '%Active%' AND (barcode.barcode = '{search_text}' or 
			item.ifw_retailskusuffix like '%{search_text}%') AND item.disabled = 0
			AND item.has_variants = 0 AND item.is_sales_item = 1
		GROUP BY
			item_code, item_name, retail_sku, template_sku
		"""
	item_data = frappe.db.sql(query ,as_dict=1)
	return item_data