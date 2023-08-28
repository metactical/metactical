import frappe

def before_save(self, method):
	self.set_status(update=True)	
	if len(self.items) > 0:
		set_default_supplier(self)
		suppliers = ''
		unique_suppliers = []
		for item in self.items:
			if item.ais_default_supplier and item.ais_default_supplier not in unique_suppliers:
				unique_suppliers.append(item.ais_default_supplier)
				if suppliers != '':
					suppliers += ', ' + item.ais_default_supplier
				else:
					suppliers += item.ais_default_supplier
		self.ais_suppliers = suppliers

def set_default_supplier(self):
	for item in self.items:
		if not item.ais_default_supplier:
			doc = frappe.get_doc('Item', item.item_code)
			for defaults in doc.item_defaults:
				if defaults.company == self.company:
					item.ais_default_supplier = defaults.default_supplier
