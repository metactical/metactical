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