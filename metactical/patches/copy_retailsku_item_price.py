import frappe

def execute():
	frappe.db.sql("""
		UPDATE
			   `tabItem Price` item_price
		INNER JOIN
			`tabItem` AS item ON item_price.item_code = item.name
		SET item_price.ifw_retailskusuffix = item.ifw_retailskusuffix
		""")