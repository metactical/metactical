import frappe
import barcode as _barcode
from io import BytesIO

def before_save(self, method):
	frappe.msgprint('Something')
	rv = BytesIO()
	_barcode.get('code128', self.name).write(rv)
	bstring = rv.getvalue()
	self.ais_barcode = bstring.decode('ISO-8859-1')

@frappe.whitelist()
def create_journal_entry(source_name, target_doc=None):
	def update_accounts(source, target):
		accounts = []
		rows = []
		for item in source.items:
			if item.income_account not in accounts:
				temp = {
					"account": item.income_account,
					"party_type": "Customer",
					"party": source.customer,
					"cost_center": item.cost_center,
					"project": item.project,
					"reference_type": "Sales Invoice",
					"reference_name": source.name,
					"debit_in_account_currency": 50
				}
		 
		
	def update_item_quantity(source, target, source_parent):
		target.qty = flt(source.qty) - flt(source.delivered_qty)
		target.stock_qty = (flt(source.qty) - flt(source.delivered_qty)) * flt(source.conversion_factor)
		target.picked_qty = flt(source.qty) - flt(source.delivered_qty)

	doc = get_mapped_doc('Sales Invoice', source_name, {
		'Sales Invoice': {
			'doctype': 'Journal Entry',
			'validation': {
				'docstatus': ['=', 1]
			}
		},
	}, target_doc, update_accounts)
	doc.purpose = 'Delivery'
	PickList.before_save = custom_before_save

	#doc.set_item_locations()

	return doc
		
