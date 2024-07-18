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

@frappe.whitelist()
def get_target_warehouse(doctype, txt, searchfield, start, page_len, filters):
	user = filters.get("user")
	warehouses = []
	if user:
		setting_exists = frappe.db.get_value("Material Request User Permission", filters={"user": user})
		if setting_exists:
			warehouses = frappe.db.sql("""SELECT warehouse FROM `tabMaterial Request Permitted Warehouse` 
							WHERE warehouse LIKE %(txt)s AND parent= %(parent)s
							AND parentfield='permitted_target_warehouse'""", 
							{
								'txt': "%%%s%%" % txt,
								'parent': setting_exists
							})
		else:
			#Retrun all warehouses
			warehouses = frappe.db.sql("""SELECT name FROM `tabWarehouse` WHERE is_group=0 AND disabled=0 AND name LIKE %(txt)s""", {'txt': "%%%s%%" % txt})
	return warehouses