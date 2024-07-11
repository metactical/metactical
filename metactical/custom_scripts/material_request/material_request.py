import frappe
from erpnext.stock.doctype.material_request.material_request import MaterialRequest
from erpnext.stock.utils import get_stock_balance

class CustomMaterialRequest(MaterialRequest):
	def before_submit(self):
		super(CustomMaterialRequest, self).before_submit()
		self.validate_item_qty()

	def validate_item_qty(self):
		if self.material_request_type == 'Material Transfer':
			for item in self.items:
				if item.from_warehouse is None or item.from_warehouse == '':
					frappe.throw(f'Source Warehouse is required for item {item.item_code}')

				if item.qty > get_stock_balance(item.item_code, item.from_warehouse):
					frappe.throw(f'Requested quantity of item {item.item_code} is greater than available quantity at warehouse')

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
