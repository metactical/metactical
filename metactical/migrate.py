import frappe

def after_migrate():
	reset_po_naming_series()
	reset_customer_naming_series()
	set_app_logo()

def reset_customer_naming_series():
	exists = frappe.db.exists('Property Setter', {'doctype_or_field': 'DocField', 'doc_type': 'Customer',
					'field_name': 'naming_series', 'property': 'options'})
	if exists:
		frappe.db.delete('Property Setter', exists)

	doc = frappe.new_doc('Property Setter')
	doc.update({
		'doctype_or_field': 'DocField',
		'doc_type': 'Customer',
		'field_name': 'naming_series',
		'property': 'options',
		'value': 'CS-.YY.-'
	})
	doc.insert()
	

def reset_po_naming_series():
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

def set_app_logo():
	# Set the logo for metactical/storebuilder
	frappe.db.set_single_value("Navbar Settings", "app_logo", "/assets/metactical/images/storebuilder-logo.png")
	frappe.db.set_single_value("System Settings", "app_name", "Storebuilder Commerce")
