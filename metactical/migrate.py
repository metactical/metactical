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

	create_store_credit_accounts()

def create_store_credit_accounts(): 
	default_company = frappe.get_single("Global Defaults").default_company

	if default_company:
		abbr = frappe.get_value("Company", default_company, "abbr")
	else:
		return

	if frappe.db.exists("Account", "Store Credits - " + abbr):
		return

	# parent account
	parent_account = get_accounts_object(default_company)
	parent_account.account_name = "Store Credits"
	parent_account.is_group = 1
	parent_account.parent_account = "Current Liabilities - " + abbr
	parent_account.save()
	frappe.db.commit()

	# child accounts
	account = get_accounts_object(default_company)
	account.account_name = "Store Credit - CAD"
	account.company = default_company
	account.parent_account = parent_account.name
	account.root_type = "Liability"
	account.save()
	frappe.db.commit()

	account = get_accounts_object(default_company)
	account.account_name = "Store Credit - USD"
	account.company = default_company
	account.parent_account = parent_account.name
	account.root_type = "Liability"
	account.save()    
	frappe.db.commit()

def get_accounts_object(default_company):
	new_account = frappe.get_doc({
		"doctype": "Account",
		"company": default_company,
		"root_type": "Liability"
	})

	return new_account