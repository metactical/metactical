import frappe

@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def shipping_address_query(doctype, txt, searchfield, start, page_len, filters):
	link_doctype = filters.pop('link_doctype')
	link_name = filters.pop('link_name')
	company = filters.pop('company')
	return frappe.db.sql('''select
			`tabAddress`.name
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
			
@frappe.whitelist()
def get_po_items(docname):
	items = []
	added_items = []
	doc = frappe.get_doc('Purchase Order', docname)
	for item in doc.items:
		if item.item_code not in added_items:
			items.append(item)
			added_items.append(item.item_code)
		else:
			for i in items:
				if i.item_code == item.item_code:
					i.update({
						'qty': i.qty + item.qty
					})
	return items
