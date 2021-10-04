import frappe

@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def shipping_address_query(doctype, txt, searchfield, start, page_len, filters):
	link_doctype = filters.pop('link_doctype')
	link_name = filters.pop('link_name')
	company = filters.pop('company')
	return frappe.db.sql('''select
			`tabAddress`.name, `tabAddress`.city, `tabAddress`.country
		from
			`tabAddress`, `tabDynamic Link`
		where
			`tabDynamic Link`.parent = `tabAddress`.name and
			`tabDynamic Link`.parenttype = 'Address' and
			ifnull(`tabAddress`.disabled, 0) = 0 and
			(`tabDynamic Link`.link_doctype = %(link_doctype)s and
			`tabDynamic Link`.link_name = %(link_name)s)
			OR 
			(`tabDynamic Link`.link_doctype = 'Company' and
			`tabDynamic Link`.link_name = %(company)s and
			`tabAddress`.is_your_company_address = 1)''',
			{'link_name': link_name, 'link_doctype': link_doctype, 'company': company}
			)
