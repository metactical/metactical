import frappe

def validate(self, method):
	if self.set_warehouse:
		for item in self.items:
			if item.warehouse != self.set_warehouse:
				item.warehouse = self.set_warehouse
			

@frappe.whitelist()
def get_pr_items(docname):
	items = []
	added_items = []
	doc = frappe.get_doc('Purchase Receipt', docname)
	for item in doc.items:
		if item.item_code not in added_items:
			items.append(item)
			added_items.append(item.item_code)
		else:
			for i in items:
				if i.item_code == item.item_code:
					i.update({
						'qty': i.qty + item.qty
					})
	return items