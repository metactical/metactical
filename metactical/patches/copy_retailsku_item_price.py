import frappe

def execute():
	item_prices = frappe.get_all('Item Price', fields=['name', 'item_code'])
	for item_price in item_prices:
		frappe.db.set_value('Item Price', item_price.name, 'ifw_retailskusuffix', frappe.db.get_value('Item', item_price.item_code, 'ifw_retailskusuffix'))