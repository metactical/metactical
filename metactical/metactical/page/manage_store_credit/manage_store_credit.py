import frappe, json

@frappe.whitelist()
def search_customer(*args, **kwargs):
    phone_number = kwargs.get('phone_number')
    email = kwargs.get('email')

    filters = {}
    if phone_number:
        filters.update({"mobile_no": ["like", "%{}%".format(phone_number)]})
    if email:
        filters.update({"email_id": ["like", "%{}%".format(email)]})

    contacts = frappe.db.get_list("Contact",
                filters=filters,
                fields=["name", "email_id", "phone", "mobile_no"]
            )

    contact_names = [c.get('name') for c in contacts]
    if not contact_names:
        return []

    customers = frappe.db.sql(""" SELECT
                                    c.name, c.first_name, c.last_name, c.ais_company as company, dl.parent, c.territory
                                FROM
                                    `tabDynamic Link` dl
                                JOIN `tabCustomer` c on dl.link_name = c.name
                                WHERE
                                    dl.link_doctype = 'Customer'
                                    AND dl.parenttype = 'Contact'
                                    AND dl.parent IN %(contact_names)s
                            """, {"contact_names": contact_names}, as_dict=True)

    for customer in customers:
        for contact in contacts:
            if customer.parent == contact.name:
                customer["email"] = contact.email_id
                customer["phone_number"] = contact.mobile_no
                        
    return customers

@frappe.whitelist()
def load_si(sales_invoice):
    items = []
    taxes = {}
    retail_skus = {}
    credit_notes_grouped = {}


    sales_invoice_doc = None
    if frappe.db.exists("Sales Invoice", sales_invoice):
        sales_invoice_doc = frappe.get_doc("Sales Invoice", sales_invoice)

        for item in sales_invoice_doc.items:
            retail_sku = frappe.db.get_value("Item", item.item_code, "ifw_retailskusuffix")
            retail_skus[item.item_code] = retail_sku
            items.append({
                "si_name": sales_invoice_doc.name,
                "retail_sku": retail_sku,
                "item_name": item.item_name,
                "rate": item.rate,
                "qty": item.qty,
                "amount": frappe.format_value(item.net_amount, {"fieldtype": "Currency"}),
                "amount_with_out_format": item.net_amount,
                "discount": item.discount_amount,
                "discount_percentage": item.discount_percentage,
                "total": frappe.format_value(item.amount, {"fieldtype": "Currency"}),
                "item_code": item.item_code,
                "discount_amount": item.discount_amount,
                "posting_date": sales_invoice_doc.posting_date,
                "customer": sales_invoice_doc.customer,
                "total_taxes_and_charges": sales_invoice_doc.total_taxes_and_charges,
                "grand_total": sales_invoice_doc.grand_total,
                "si_discount_amount": sales_invoice_doc.discount_amount,
            })

        if not sales_invoice_doc.is_return:
            taxes_list = []
            for tax in sales_invoice_doc.taxes:
                taxes_list.append({
                    "name": tax.charge_type,
                    "amount": frappe.format_value(tax.tax_amount, {"fieldtype": "Currency"}),
                    "rate": tax.rate,
                })
            
            taxes["taxes"] = taxes_list
            taxes["TTL Tax"] = frappe.format_value(sales_invoice_doc.total_taxes_and_charges, {"fieldtype": "Currency"}) if sales_invoice_doc else "0"
            taxes["Discount"] = frappe.format_value(sales_invoice_doc.discount_amount, {"fieldtype": "Currency"}) if sales_invoice_doc else ""
            taxes["TTL Store Credit"] = frappe.format_value(sales_invoice_doc.grand_total, {"fieldtype": "Currency"}) if sales_invoice_doc else ""
            taxes["Total Qty Returned"] = sales_invoice_doc.total_qty if sales_invoice_doc else ""
    
        if sales_invoice_doc.is_return:
            credit_notes = items
            items = []
        else:
            credit_notes = frappe.db.sql(""" SELECT
                                                si.name as si_name, sii.item_code, sii.item_name, sii.qty, sii.rate, 
                                                sii.discount_amount, sii.amount, si.posting_date, si.customer,
                                                si.total_taxes_and_charges, si.grand_total, si.discount_amount as si_discount_amount,
                                                sii.discount_percentage
                                            FROM
                                                `tabSales Invoice` si
                                            JOIN `tabSales Invoice Item` sii ON si.name = sii.parent
                                            WHERE
                                                return_against = %(sales_invoice)s
                                            ORDER BY
                                                posting_date DESC, sii.idx ASC
                                        """, {"sales_invoice": sales_invoice_doc.name}, as_dict=True)

        # group credit notes by sales invoice
        for credit_note in credit_notes:
            if items:
                credit_note["retail_sku"] = retail_skus.get(credit_note["item_code"])
                credit_note["amount"] = frappe.format_value(credit_note["amount"], {"fieldtype": "Currency"})
                # credit_note["discount_amount"] = frappe.format_value(credit_note.discount_amount, {"fieldtype": "Currency"})
                credit_note["total_taxes_and_charges"] = frappe.format_value(credit_note["total_taxes_and_charges"], {"fieldtype": "Currency"})
                credit_note["grand_total"] = frappe.format_value(credit_note["grand_total"], {"fieldtype": "Currency"})
                # credit_note["si_discount_amount"] = frappe.format_value(credit_note.si_discount_amount, {"fieldtype": "Currency"})
                # credit_note["rate"] = frappe.format_value(credit_note.rate, {"fieldtype": "Currency"})

            credit_notes_grouped.setdefault(credit_note["si_name"], []).append(credit_note)

    frappe.response["items"] = items
    frappe.response["taxes"] = taxes
    frappe.response["customer"] = sales_invoice_doc.customer if sales_invoice_doc else ""
    frappe.response["credit_notes"] = credit_notes_grouped

@frappe.whitelist()
def create_customer(**kwargs):
    try:
        customer = json.loads(frappe.form_dict.customer)
        
        # create customer
        customer_doc = frappe.new_doc("Customer")
        customer_doc.first_name = customer.get('first_name')
        customer_doc.last_name = customer.get('last_name')
        customer_doc.ais_company = customer.get('company')
        customer_doc.ifw_email = customer.get('email')
        customer_doc.customer_name = "{} {}".format(customer.get('first_name'), customer.get('last_name'))
        customer_doc.default_currency = "CAD"
        customer_doc.territory = customer.get('territory')
        customer_doc.insert()

        # create contact
        contact_doc = frappe.get_doc({
            "doctype": "Contact",
            "first_name": customer.get('first_name'),
            "last_name": customer.get('last_name'),
            "email_id": customer.get('ifw_email'),
            "phone": customer.get('phone'),
            "mobile_no": customer.get('phone'),
            "links": [{
                "link_doctype": "Customer",
                "link_name": customer_doc.name
            }],
            "email_ids": [{
                "email_id": customer.get('email'),
                "is_primary": 1
            }],
            "phone_nos": [{
                "phone": customer.get('phone_number'),
                "is_primary_mobile_no": 1
            }]
        })

        contact_doc.insert()
        frappe.db.set_value("Customer", customer_doc.name, "customer_primary_contact", contact_doc.name)

        frappe.db.commit()
        frappe.response["customer"] = customer_doc.name
        frappe.response["success"] = True
    except Exception as e:
        frappe.response["error"] = str(e)
        frappe.response["success"] = False
        frappe.log_error(title="Create Customer Error (Transfer Store Credit Page)", message=frappe.get_traceback())
        frappe.db.rollback()
