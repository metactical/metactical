import frappe, json
from frappe.utils.background_jobs import enqueue

@frappe.whitelist()
def search_customer(*args, **kwargs):
    try:
        phone_number = kwargs.get('phone_number')
        email = kwargs.get('email')
        first_name = kwargs.get('first_name')
        last_name = kwargs.get('last_name')

        # search by phone number
        contacts_for_phone_number = []
        if phone_number:
            filters = {"mobile_no": ["like", "%{}%".format(phone_number)]}
            contacts_for_phone_number = frappe.db.get_list("Contact",
                        filters=filters,
                        fields=["name", "email_id", "phone", "mobile_no"]
                    )

        # search by email
        contacts_for_email = []
        if email:
            filters = {"email_id": ["like", "%{}%".format(email)]}
            contacts_for_email = frappe.db.get_list("Contact",
                        filters=filters,
                        fields=["name", "email_id", "phone", "mobile_no"]
                    )

        contacts = contacts_for_phone_number + contacts_for_email
        contact_names = [c.get('name') for c in contacts]

        # search by last name and first name
        customer_names = ""
        if first_name or last_name:
            filters = {
                "first_name": ["like", "%{}%".format(first_name)],
                "last_name": ["like", "%{}%".format(last_name)]
            }
            
            customer_names = frappe.db.get_list("Customer",
                        filters=filters,
                        fields=["name"]
                    )
            customer_names = [c.get('name') for c in customer_names]

        if not contact_names and not customer_names:
            frappe.response["customers"] = []
            frappe.response["success"] = True
            return

        search_filter = get_search_filter(contact_names, customer_names)
        customers = frappe.db.sql(f""" SELECT
                                        c.name, c.first_name, c.last_name, c.ais_company as company, dl.parent, c.territory, ct.email_id, ct.mobile_no, ct.phone
                                    FROM
                                        `tabDynamic Link` dl
                                    JOIN `tabCustomer` c on dl.link_name = c.name
                                    JOIN `tabContact` ct on dl.parent = ct.name
                                    WHERE
                                        dl.link_doctype = 'Customer'
                                        AND dl.parenttype = 'Contact'
                                        AND ({search_filter})
                                """, as_dict=True)

        for customer in customers:
            customer["phone_number"] = customer.mobile_no
            if not customer.mobile_no and not customer.phone:
                customer["phone_number"] = customer.phone
            
            customer["email"] = customer.email_id
                            
        frappe.response["customers"] = customers
        frappe.response["success"] = True
    except Exception as e:
        frappe.log_error(title="Search Customer Error (Transfer Store Credit Page)", message=frappe.get_traceback())
        frappe.response["success"] = False

def get_search_filter(contact_names, customer_names):
    contact_filter_query = ""
    # contact_names = list(set(contact_names))
    if contact_names:
        formatted_tuple = str(tuple(contact_names))
        if formatted_tuple.endswith(",)"):
            formatted_tuple = formatted_tuple[1:-2]
        else:
            formatted_tuple = formatted_tuple[1:-1]

        contact_filter_query = f"dl.parent IN ({formatted_tuple})"

    customer_filter_query = ""
    if customer_names:
        formatted_tuple = str(tuple(customer_names))[1:-2]
        customer_filter_query = f"c.name IN ({formatted_tuple})"

    search_filter = ""
    if customer_filter_query and contact_filter_query:
        search_filter = f"({contact_filter_query} or {customer_filter_query})"
    elif customer_filter_query:
        search_filter = customer_filter_query
    elif contact_filter_query:
        search_filter = contact_filter_query

    return search_filter


@frappe.whitelist()
def load_si(sales_invoice):
    items = []
    taxes = {}
    retail_skus = {}
    credit_notes_grouped = {}

    sales_invoice_doc = None
    if frappe.db.exists("Sales Invoice", sales_invoice):
        sales_invoice_doc = frappe.get_doc("Sales Invoice", sales_invoice)
        if (sales_invoice_doc.docstatus > 1):
            frappe.throw("Sales Invoice is "+sales_invoice_doc.get("status"))
            return
        elif sales_invoice_doc.docstatus == 0:
            frappe.throw("Sales Invoice "+sales_invoice+" is a Draft")
            return
        elif sales_invoice_doc.status not in ["Paid", "Credit Note Issued"]:
            frappe.throw("Sales Invoice "+sales_invoice+" is "+sales_invoice_doc.get("status"))
            return
        
        for item in sales_invoice_doc.items:
            retail_sku = frappe.db.get_value("Item", item.item_code, "ifw_retailskusuffix")
            retail_skus[item.item_code] = retail_sku
            items.append({
                "name": item.name,
                "si_name": sales_invoice_doc.name,
                "retail_sku": retail_sku,
                "item_name": item.item_name,
                "rate": item.rate,
                "price_list_rate": item.price_list_rate,
                "qty": item.qty,
                "amount": frappe.format_value(item.net_amount, {"fieldtype": "Currency"}),
                "amount_with_out_format": item.net_amount,
                "discount": item.price_list_rate - item.rate if item.price_list_rate else item.rate,
                "discount_percentage": item.discount_percentage,
                "total": frappe.format_value(item.amount, {"fieldtype": "Currency"}),
                "item_code": item.item_code,
                "discount_amount": item.price_list_rate - item.rate if item.price_list_rate else item.rate,
                "posting_date": sales_invoice_doc.posting_date,
                "customer": sales_invoice_doc.customer,
                "total_taxes_and_charges": sales_invoice_doc.total_taxes_and_charges,
                "grand_total": sales_invoice_doc.grand_total,
                "si_discount_amount": sales_invoice_doc.discount_amount,
                "original_price": item.rate,
                "original_qty": item.qty,
            })

        if not sales_invoice_doc.is_return:
            taxes_list = []
            for tax in sales_invoice_doc.taxes:
                taxes_list.append({
                    "name": tax.charge_type,
                    "amount": frappe.format_value(tax.tax_amount, {"fieldtype": "Currency"}),
                    "rate": tax.rate,
                    "account_head": tax.account_head,
                    "description": tax.description
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
                                                si.neb_store_credit_beneficiary,
                                                si.total_taxes_and_charges, si.grand_total, si.discount_amount as si_discount_amount,
                                                sii.discount_percentage
                                            FROM
                                                `tabSales Invoice` si
                                            JOIN `tabSales Invoice Item` sii ON si.name = sii.parent
                                            WHERE
                                                return_against = %(sales_invoice)s and si.docstatus = 1
                                            ORDER BY
                                                si.creation DESC, sii.idx ASC
                                        """, {"sales_invoice": sales_invoice_doc.name}, as_dict=True)

        # group credit notes by sales invoice
        for credit_note in credit_notes:
            if items:
                credit_note["retail_sku"] = retail_skus.get(credit_note["item_code"])
                credit_note["amount"] = frappe.format_value(credit_note["amount"], {"fieldtype": "Currency"})
                # credit_note["discount_amount"] = frappe.format_value(credit_note.discount_amount, {"fieldtype": "Currency"})
                credit_note["total_taxes_and_charges"] = frappe.format_value(credit_note["total_taxes_and_charges"], {"fieldtype": "Currency"})
                credit_note["grand_total"] = frappe.format_value(credit_note["grand_total"], {"fieldtype": "Currency"})
        
            credit_notes_grouped.setdefault(credit_note["si_name"], []).append(credit_note)

    frappe.response["items"] = items
    frappe.response["taxes"] = taxes
    frappe.response["customer"] = sales_invoice_doc.customer if sales_invoice_doc else ""
    frappe.response["credit_notes"] = credit_notes_grouped

@frappe.whitelist()
def transfer_store_credit(**kwargs):
    original_sales_invoice = frappe.form_dict.sales_invoice
    try:
        sales_invoice = frappe.form_dict.sales_invoice
        if frappe.cache().hget("store_credit", sales_invoice):
            frappe.response["success"] = False
            frappe.response["error"] = "Store Credit Transfer is already in progress. Please wait for the process to complete."
            return

        items = json.loads(kwargs.get('items'))
        customer = frappe.form_dict.customer
        tax_types = json.loads(kwargs.get('tax_types'))
        
        selected_items = []
        for item in items:
            item_doc = frappe.get_doc("Sales Invoice Item", item.get('name'))
            new_item = {}
            new_item["item_code"] = item.get('item_code')
            new_item["rate"] = item.get('rate')
            new_item["discount_amount"] = item.get('discount_amount')
            new_item["discount_percentage"] = item.get('discount_percentage')
            new_item["qty"] = -1 * float(item.get('qty'))

            selected_items.append(new_item)

        taxes = []
        for tax in tax_types:
            taxes.append({
                "charge_type": tax.get('name'),
                "rate": tax.get('rate'),
                "account_head": tax.get('account_head'),
                "description": tax.get('description')
            })

        sales_invoice = frappe.get_doc({
            "doctype": "Sales Invoice",
            "customer": frappe.db.get_value("Sales Invoice", sales_invoice, "customer"),
            "is_return": 1,
            "neb_store_credit_beneficiary": customer,
            "return_against": sales_invoice,
            "posting_date": frappe.utils.nowdate(),
            "items": selected_items,
            "taxes_and_charges": frappe.get_value("Sales Invoice", sales_invoice, "taxes_and_charges"),
            "taxes": taxes, 
            "disable_rounded_total": 1,
        })

        frappe.cache().hset("store_credit", sales_invoice.return_against, sales_invoice.return_against)
        enqueue(save_and_submit_store_credit, sales_invoice=sales_invoice, customer=customer, queue='long', timeout=1500)

        # update customer price list if there is no default price list
        customer_price_list = frappe.db.get_value("Customer", customer, "default_price_list")
        if not customer_price_list:
            pos_profile = frappe.db.get_value("Sales Invoice", sales_invoice.return_against, "pos_profile")
            price_list = get_price_list(pos_profile)
            frappe.db.set_value("Customer", customer, "default_price_list", price_list)

        frappe.response["items"] = [item.get('name') for item in items]
        frappe.response["success"] = True
        frappe.response["sales_invoice"] = sales_invoice.name
        frappe.msgprint("Background Job Started to Transfer Store Credit. You will be notified once it is completed.")
    except Exception as e:
        frappe.db.rollback()
        frappe.cache().delete_value("store_credit", original_sales_invoice)
        frappe.response["error"] = frappe.get_traceback()
        frappe.response["success"] = False
        frappe.log_error(title="Transfer Store Credit Error (Transfer Store Credit Page)", message=frappe.get_traceback())

def save_and_submit_store_credit(sales_invoice, customer):
    try:
        sales_invoice.save()
        sales_invoice.submit()
        create_journal_entry(sales_invoice, customer)
        frappe.db.commit()
        
        frappe.cache().delete_value("store_credit", sales_invoice.return_against)
        frappe.publish_realtime("transfer_store_credit", 
                                {
                                    "sales_invoice": sales_invoice.return_against, 
                                    "new_sales_invoice": sales_invoice.name,
                                    "error": ""
                                }, 
                                user=frappe.session.user)
    except Exception as e:
        frappe.cache().delete_value("store_credit", sales_invoice.return_against)
        frappe.log_error(title="Save and Submit Store Credit Error (Transfer Store Credit Page)", message=frappe.get_traceback())
        frappe.db.rollback()
        frappe.publish_realtime("transfer_store_credit", {"error": str(e)}, user=frappe.session.user)

def create_journal_entry(sales_invoice, customer):
    if sales_invoice.currency == "CAD":
        store_credit_account = frappe.db.get_single_value("Metactical Settings", "store_credit_account_cad")
    elif sales_invoice.currency == "USD":
        store_credit_account = frappe.db.get_single_value("Metactical Settings", "store_credit_account_usd")
        
    if not store_credit_account:
        frappe.publish_realtime("transfer_store_credit", {"error": "Store Credit Account not set in Metactical Settings. Please create the Journal Entry manually."}, user=frappe.session.user)

    main_sales_invoice = frappe.db.get_values("Sales Invoice", {"name": sales_invoice.return_against}, ["debit_to", "company", "customer", "name"], as_dict=True)[0]
    
    je = frappe.new_doc("Journal Entry")
    je.voucher_type = "Journal Entry"
    je.posting_date = frappe.utils.nowdate()
    je.company = main_sales_invoice.company
    je.user_remark = "Store Credit Transfer from Sales Invoice {} to Customer {}".format(sales_invoice.return_against, customer)
    je.append("accounts", {
        "account": store_credit_account,
        "party_type": "Customer",
        "party": customer,
        "credit_in_account_currency": -1 * sales_invoice.grand_total,
        "is_advance": "Yes"
    })
    je.append("accounts", {
        "account": main_sales_invoice.debit_to,
        "debit_in_account_currency": -1 * sales_invoice.grand_total,
        "reference_type": "Sales Invoice",
        "reference_name": main_sales_invoice.name,
        "party_type": "Customer",
        "party": main_sales_invoice.customer,
        "is_advance": "No"
    })

    je.insert()
    je.submit()

@frappe.whitelist()
def create_customer(**kwargs):
    try:
        customer = json.loads(frappe.form_dict.customer)
        
        if frappe.db.exists("Contact", {"email_id": customer.get('email'), "mobile_no": customer.get('phone_number')}):
            frappe.throw("Customer with email <b>{}</b> and <b>{}</b> already exists".format(customer.get('email'), customer.get('phone_number')))

        # create customer
        customer_doc = frappe.new_doc("Customer")
        customer_doc.first_name = customer.get('first_name')
        customer_doc.last_name = customer.get('last_name')
        customer_doc.ais_company = customer.get('company')
        customer_doc.ifw_email = customer.get('email')
        customer_doc.customer_group = "Retail"
        customer_doc.customer_name = "{} {}".format(customer.get('first_name'), customer.get('last_name'))
        customer_doc.default_currency = "CAD"
        customer_doc.territory = customer.get('territory')
        customer_doc.insert()

        # create contact
        contact_doc = frappe.get_doc({
            "doctype": "Contact",
            "first_name": customer.get('first_name'),
            "last_name": customer.get('last_name'),
            "email_id": customer.get('email'),
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

@frappe.whitelist()
def create_pdf(sales_invoice, print_format="Standard"):
    pdf = frappe.get_print("Sales Invoice", sales_invoice, print_format, as_pdf=True)
    frappe.local.response.filename = "{}.pdf".format(sales_invoice)
    frappe.local.response.filecontent = pdf
    frappe.local.response.type = "download"

def get_price_list(pos_profile):
    price_list = frappe.db.get_value("POS Profile", pos_profile, "selling_price_list")
    return price_list