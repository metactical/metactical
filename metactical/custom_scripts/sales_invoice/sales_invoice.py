import frappe
import barcode as _barcode
from io import BytesIO
from frappe.model.mapper import get_mapped_doc, map_child_doc

def before_save(self, method):
	rv = BytesIO()
	_barcode.get('code128', self.name).write(rv)
	bstring = rv.getvalue()
	self.ais_barcode = bstring.decode('ISO-8859-1')

@frappe.whitelist()
def create_journal_entry(source_name, bank_cash, amount, target_doc=None):
	def update_accounts(source_doc, target_doc):
		amount_after_tax = float(amount)
		target_doc.accounts = []
		#Add taxes and charges
		for row in source_doc.taxes:
			tax_amount = (float(amount) * float(row.rate))/100
			amount_after_tax = amount_after_tax - tax_amount
			account = frappe.new_doc('Journal Entry Account')
			account.update({
				"account": row.account_head,
				"cost_center": source_doc.items[0].cost_center,
				"project": source_doc.items[0].project,
				"debit_in_account_currency": tax_amount
			})
			target_doc.append("accounts", account)
			
		#For the simplest implementation, we assume all items on the invoice share the same income account
		account = frappe.new_doc('Journal Entry Account')
		account.update({
			"account": source_doc.items[0].income_account,
			"cost_center": source_doc.items[0].cost_center,
			"project": source_doc.items[0].project,
			"debit_in_account_currency": amount_after_tax
		})
		target_doc.append("accounts", account)
		
		account = frappe.new_doc('Journal Entry Account')
		account.update({
			"account": source_doc.debit_to,
			"reference_type": "Sales Invoice",
			"party_type": "Customer",
			"party": source_doc.customer,
			"reference_name": source_name,
			"credit_in_account_currency": amount
		})
		target_doc.append("accounts", account)
		
		account = frappe.new_doc('Journal Entry Account')
		account.update({
			"account": source_doc.debit_to,
			"reference_type": "Sales Invoice",
			"party_type": "Customer",
			"party": source_doc.customer,
			"reference_name": source_name,
			"debit_in_account_currency": amount
		})
		target_doc.append("accounts", account)
		
		account = frappe.new_doc('Journal Entry Account')
		account.update({
			"account": bank_cash,
			"credit_in_account_currency": amount
		})
		target_doc.append("accounts", account)

	target_doc = frappe.new_doc('Journal Entry')
	target_doc.update({
		"voucher_type": "Credit Note"
	})
	source_doc = frappe.get_doc('Sales Invoice', source_name)
	update_accounts(source_doc, target_doc)
	return target_doc
		
