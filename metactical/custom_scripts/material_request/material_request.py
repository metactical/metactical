import frappe
from erpnext.stock.doctype.material_request.material_request import MaterialRequest
from erpnext.stock.utils import get_stock_balance
import json

class CustomMaterialRequest(MaterialRequest):
	def before_submit(self):
		super(CustomMaterialRequest, self).before_submit()
		self.validate_item_qty()
		self.validate_qoh()

	def validate_item_qty(self):
		if self.material_request_type == 'Material Transfer':
			for item in self.items:
				if item.from_warehouse is None or item.from_warehouse == '':
					frappe.throw(f'Source Warehouse is required for item {item.item_code}')

				# if item.qty > get_stock_balance(item.item_code, item.from_warehouse):
				# 	frappe.throw(f'Requested quantity of item {item.item_code} is greater than available quantity at warehouse')

	def validate_qoh(self):
		# check if a qty greater than the quantity on hand is entered
		if self.material_request_type == "Material Transfer":
			items = []
			for item in self.items:
				if item.qty > item.qoh:
					items.append(item.item_code) 

			if items:
				message = 'The quantities of these items exceed the available warehouse stock. <br>'
				message += "<b>" + ', '.join(items) + "</b>"
				frappe.msgprint(message)

	def before_save(self):
		self.set_status(update=True)	
		if len(self.items) > 0:
			self.set_default_supplier()
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

@frappe.whitelist()
def get_qoh(filters):
	filters = json.loads(filters)
	updated_qty = []

	for value in filters:
		qty = 0
		data= frappe.db.sql("""select actual_qty-reserved_qty AS qty from `tabBin`
			where item_code = %s and warehouse=%s
			""",(value['item'], value["warehouse"]), as_dict=1)
		if data and data[0]['qty'] > 0:
			qty = data[0]['qty']
		
		updated_qty.append({
			'item_code': value['item'],
			'qty': qty,
			'name': value['name']
		})

	return updated_qty