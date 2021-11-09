import frappe

def remove_item_defaults():
	frappe.set_user('Administrator')
	items = frappe.get_all('Item')
	for item in items:
		if '_Test' in str(item):
			continue
		doc = frappe.get_doc('Item', item)
		to_save = False
		if len(doc.item_defaults) > 0:
			for default in doc.item_defaults:
				if default.default_supplier or default.default_price_list or default.default_warehouse:
					to_save = True
					default.update({
						"default_supplier": '',
						"default_price_list": '',
						"default_warehouse": ''
					})
		if to_save:
			doc.save()
		print({'item': item, 'to_save': to_save})
