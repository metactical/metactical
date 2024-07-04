import frappe

def after_migrate():
	#Reset naming series in PO based on site name
	exists = frappe.db.exists('Property Setter', {'doctype_or_field': 'DocField', 'doc_type': 'Purchase Order',
					'field_name': 'naming_series', 'property': 'options'})
	if exists:
		doc = frappe.db.get_value('Property Setter', {'doctype_or_field': 'DocField', 'doc_type': 'Purchase Order',
					'field_name': 'naming_series', 'property': 'options'}, 'name')
		frappe.db.delete('Property Setter', doc)
		
	site = frappe.local.site
	value = '.YYYY.-'
	if site == 'usa.metactical.com':
		value = '3002-'
	doc = frappe.new_doc('Property Setter')
	doc.update({
		'doctype_or_field': 'DocField', 
		'doc_type': 'Purchase Order',
		'field_name': 'naming_series', 
		'property': 'options',
		'value': value
	})
	doc.insert()

	update_payment_completed_at()

def update_payment_completed_at():
	# Update neb_payment_completed_at in Sales Invoice
	frappe.db.sql("""UPDATE `tabSales Invoice` SET neb_payment_completed_at=posting_date WHERE neb_payment_completed_at is NULL and status='Paid'""")
	
	# update neb_payment_completed_at in Sales Order
	frappe.db.sql("""UPDATE `tabSales Order` SET neb_payment_completed_at=transaction_date WHERE neb_payment_completed_at is NULL and billing_status='Fully Paid'""")