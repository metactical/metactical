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

    print(filters)

    contacts = frappe.db.get_list("Contact",
                or_filters=filters,
                fields=["name", "email_id", "phone", "mobile_no"]
            )

    contact_names = [c.get('name') for c in contacts]
    print(contact_names)
    if not contact_names:
        return []

    customers = frappe.db.sql(""" SELECT
                                    c.name, c.first_name, c.last_name, c.ais_company as company, dl.parent
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
            print(customer.parent, contact.name, customer.parent == contact.name)
            if customer.parent == contact.name:
                customer["email"] = contact.email_id
                customer["phone_number"] = contact.mobile_no
                        
    return customers

@frappe.whitelist()
def load_si(sales_invoice):
    items = []
    taxes = {}

    sales_invoice_doc = None
    if frappe.db.exists("Sales Invoice", sales_invoice):
        sales_invoice_doc = frappe.get_doc("Sales Invoice", sales_invoice)

        for item in sales_invoice_doc.items:
            retail_sku = frappe.db.get_value("Item", item.item_code, "ifw_retailskusuffix")
            items.append({
                "name": item.name,
                "retail_sku": retail_sku,
                "item_name": item.item_name,
                "rate": item.rate,
                "qty": item.qty,
                "amount": frappe.format_value(item.net_amount, {"fieldtype": "Currency"}),
                "amount_with_out_format": item.net_amount,
                "discount": item.discount_amount
            })

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
        
    frappe.response["items"] = items
    frappe.response["taxes"] = taxes
    frappe.response["customer"] = sales_invoice_doc.customer if sales_invoice_doc else ""

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
        customer_doc.default_currency = "USD"
        customer_doc.territory = "Ontario"
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

        frappe.db.commit()
        frappe.response["customer"] = customer_doc.name
        frappe.response["success"] = True
    except Exception as e:
        frappe.response["error"] = str(e)
        frappe.response["success"] = False
        frappe.log_error(title="Create Customer Error (Transfer Store Credit Page)", message=frappe.get_traceback())
        frappe.db.rollback()
