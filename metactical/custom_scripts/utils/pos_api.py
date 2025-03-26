import frappe
from metactical.custom_scripts.sales_order.sales_order import make_sales_invoice
from metactical.custom_scripts.utils.metactical_utils import ( 
	post_to_rocket_chat, queue_action
)
from frappe.utils import file_lock, now_datetime, get_url

@frappe.whitelist()
def receive_pos_data(*args, **kwargs):
    form_data = dict(frappe.form_dict)
    frappe.log_error("POS Data", form_data)

    user_validation = validate_users(form_data)
    if not user_validation["success"]:
        frappe.response["Status"] = "500"
        frappe.response["Message"] = [user_validation["error"]]
        frappe.response["InvoiceId"] = None
        frappe.response["Total"] = 0.0
        return
        
    try:        
        # Do something with the data
        customer = get_customer(form_data)
        if not customer:
            frappe.response["Status"] = "500"
            frappe.response["Message"] = ["Unable to create/find Customer"]
            frappe.response["InvoiceId"] = None
            frappe.response["Total"] = 0.0
            return
            
        sales_order = create_sales_order(form_data, customer)
        if not sales_order["success"]:
            frappe.response["Status"] = "500"
            frappe.response["Message"] = [sales_order["error"]]
            frappe.response["InvoiceId"] = None
            frappe.response["Total"] = 0.0
            return
        
        sales_order = sales_order["sales_order"]
        if sales_order:
            frappe.enqueue(
                submit_sales_order,
                queue="default", # one of short, default, long
                at_front=True,
                form_data=form_data,
                sales_order=sales_order.name
            )
                                    
            frappe.enqueue(
                create_comments,
                queue="default", # one of short, default, long
                form_data=form_data,
                sales_order=sales_order.name
            )
                
        frappe.response["Status"] = "200"
        frappe.response["InvoiceId"] = sales_order.name
        frappe.response["Message"] = []
        frappe.response["Total"] = float(sales_order.grand_total)
            
    except Exception as e:
        frappe.log_error(title="pos_data", message=form_data)
        frappe.log_error(title='Receive POS Data Error', message=frappe.get_traceback())
        frappe.clear_last_message()
        frappe.response["Status"] = "500"
        frappe.response["Message"] = [str(e)]
        frappe.response["InvoiceId"] = None
        frappe.response["Total"] = 0.0
        
def validate_users(form_data):
    # Check if SalesPerson exists
    if "SalesPerson" not in form_data:
        return {"error": "SalesPerson is required", "success": False}
    else:
        if not frappe.db.exists('User', form_data['SalesPerson']):
            return {"error": "User {0} does not exist".format(form_data['SalesPerson']), "success": False} 
    
    approvers = form_data["ApprovalList"]
    pos_profile = form_data["POSProfile"] + ' Operators'
    
    if not frappe.db.exists('POS Profile', pos_profile):
        return {"error": "POS Profile {0} does not exist".format(pos_profile), "success": False}

    # get all users that are allowed to use the POS Profile
    pos_profile_users = frappe.get_doc('POS Profile', pos_profile).applicable_for_users
    users = {}
    
    for user in pos_profile_users:
        users[user.user] = {
            "ifw_is_main_pos_user": user.ifw_is_main_pos_user,
            "ifw_max_discount_percent": user.ifw_max_discount_percent,
        }
        
    if form_data["SalesPerson"] not in users:
        return {"error": "User {0} is not allowed to make POS transactions for {1} profile".format(form_data["SalesPerson"], pos_profile), "success": False}
        
    # Check if approvers list is availble in the incoming api request
    if "ApprovalList" not in form_data:
        return {"success": True}   

    for approver in approvers:
        approver = frappe.db.get_value('User', {'full_name': approver["ManagerId"]}, 'name')
        if approver not in users:
            return {"error": "User {0} is not allowed to approve POS transactions".format(approver), "success": False}
        else:
            if not users[approver]["ifw_is_main_pos_user"]:
                return {"error": "User {0} is not allowed to approve Discounts in POS transactions for {1} profile".format(approver, pos_profile), "success": False}
            if users[approver]["ifw_max_discount_percent"] < form_data['OverallDiscount']:
                return {"error": "User {0} is not allowed to approve POS transactions with discount greater than {1}%".format(approver, users[approver]["ifw_max_discount_percent"]), "success": False}
            
    return {"success": True}
                
                   
def create_sales_order(form_data, customer):
    items = form_data['Items']
    taxes = form_data['Taxes']
    company_address = frappe.db.get_value("POS Profile", form_data['POSProfile'] + ' Operators', 'company_address')
    if not company_address:
        return {"success": False, "error": "Company Address not found for {0}".format(form_data['POSProfile'] + ' Operators')}
    
    so_data = {
        'doctype': 'Sales Order',
        'customer': customer,
        'taxes_and_charges': form_data['TaxesAndChargesTemplate'],
        'delivery_date': frappe.utils.today(),
        'company_address': company_address,
        'source': form_data['LeadSource'],
        'ignore_pricing_rule': 1,
        'contact_person': frappe.db.get_value('Customer', customer, 'customer_primary_contact'),
        'additional_discount_percentage': form_data['OverallDiscount'],
        "owner": form_data['SalesPerson'],
    }
        
    items = get_items(form_data)
    so_data.update({'items': items})
    
    taxes = get_taxes(form_data)
    so_data.update({'taxes': taxes})
        
    frappe.set_user(form_data['SalesPerson'])
    sales_order = frappe.get_doc(so_data)

    sales_order.insert(ignore_permissions=True)
    frappe.set_user("Administrator")
    frappe.db.commit()
            
    return {"success": True, "sales_order": sales_order}

def submit_sales_order(sales_order, form_data):
    frappe.set_user(form_data["SalesPerson"])
    try:
        sales_order = frappe.get_doc('Sales Order', sales_order)
        sales_order.submit()    
        frappe.db.commit()    
    except Exception as e:
        frappe.set_user("Administrator")
        frappe.log_error(title='Submit Sales Order Error', message=frappe.get_traceback())
        
        if type(sales_order) == str:
            sales_order = frappe.get_doc('Sales Order', sales_order)
        
        # add comment to sales order
        comment = {"comment_by": form_data['SalesPerson'], "comment": str(e)}    
        create_comment(comment, form_data['SalesPerson'], sales_order.name)
        
        url = "/app/{0}/{1}".format(sales_order.doctype.lower().replace(" ", "-"), sales_order.name)
        message = "Unable to submit Sales Order created by POS. Please check the document and resubmit. \n[{0}]({1})".format(get_url(url), get_url(url))
        post_to_rocket_chat(sales_order, message, pos=True)
        
        add_payment_info_to_sales_order(sales_order, form_data)

        return
    
    sales_invoice = None
    try:
        sales_invoice = create_invoice(sales_order, form_data)
        frappe.db.commit()
    except Exception as e:
        frappe.set_user("Administrator")
        frappe.log_error(title='Create Invoice Error', message=frappe.get_traceback())
        
        # add comment to sales order
        comment = {"comment_by": form_data['SalesPerson'], "comment": str(e)}
        create_comment(comment, form_data['SalesPerson'], sales_order.name)
        
        # post to rocket chat
        url = "/app/{0}/{1}".format(sales_order.doctype.lower().replace(" ", "-"), sales_order.name)
        message = "Unable to create Invoice for Sales Order created by POS. Please check the document and resubmit. \n[{0}]({1})".format(get_url(url), get_url(url))
        post_to_rocket_chat(sales_order, message, pos=True)
        
        # add payment info to sales order
        add_payment_info_to_sales_order(sales_order, form_data)

        return
    
    if sales_invoice:
        queue_action(sales_invoice, 'submit')
        frappe.set_user("Administrator")

def add_payment_info_to_sales_order(sales_order, form_data):
    if "Payment" not in form_data:
        return
    
    message = ""
    for payment in form_data['Payment']:
        message += "Payment of <b>$ {0}</b> made using <b>{1}</b> <br>".format(payment['Amount'], payment['ModeOfPayment'])
        
    if message:
        frappe.get_doc({
            'doctype': 'Comment',
            'comment_by': form_data['SalesPerson'],
            'content': message,
            'reference_doctype': 'Sales Order',
            "comment_type": "Comment",
            'reference_name': sales_order.name,
        }).save(ignore_permissions=True)

def create_comments(sales_order, form_data):
    comments = get_comments(form_data)
    for comment in comments:
        commentor = frappe.db.get_value('User', {'full_name': comment['comment_by']}, 'email')
        frappe.set_user(commentor)
        create_comment(comment, commentor, sales_order)
    frappe.set_user("Administrator")
    frappe.db.commit()
    
def create_comment(comment, commentor, sales_order):
    frappe.get_doc({
        'doctype': 'Comment',
        'comment_email': commentor,
        'comment_by': comment['comment_by'],
        'content': comment['comment'],
        'reference_doctype': 'Sales Order',
        "comment_type": "Comment",
        'reference_name': sales_order,
    }).save(ignore_permissions=True)
    frappe.db.commit()
    
def create_invoice(sales_order, form_data):
    sales_invoice = make_sales_invoice(sales_order.name)
    sales_invoice.is_pos = 1
    sales_invoice.update_stock = 1
    sales_invoice.pos_profile = form_data['POSProfile'] + ' Operators'
    frappe.set_user(form_data['SalesPerson'])
    payments = get_payments(form_data)
    sales_invoice.update({'payments': payments})
    sales_invoice.save()

    frappe.set_user("Administrator")    
    return sales_invoice
    
def get_taxes(form_data):  
    taxes = []
    company = frappe.db.get_single_value('Global Defaults', 'default_company')
    company_abr = frappe.db.get_value('Company', company, 'abbr')
    
    for tax in form_data['Taxes']:
        taxes.append({
            'charge_type': 'On Net Total',
            'account_head': tax['TaxId'] + ' - ' + company_abr,
            'description': tax['TaxId'],
            'rate': tax['Amount'],
        })
            
    return taxes
            
def get_items(form_data):
    items = []
    warehouse = frappe.db.get_value('POS Profile', form_data['POSProfile'] + ' Operators', 'warehouse')
    for item in form_data['Items']:
        item_code = item['ItemCode']
        rate = item['Rate']
        qty = item['Qty']
        item_name = item['ItemName'] if 'ItemName' in item else ''
        
        item_info = {
            'item_code': item_code,
            'price_list_rate': rate,
            'qty': qty,
            'discount_percentage': item['Discount'],
            'warehouse': warehouse if warehouse else 'W01-WHS-Active Stock - ICL'
        }

        if item_code == "2":
            item_info.update({'item_name': item_name})
        
        items.append(item_info)
        
    return items
    
def get_customer(form_data):
    frappe.set_user(form_data['SalesPerson'])
    try:

        if not form_data['Customer']['Name']:
            frappe.set_user("Administrator")
            return "DefaultPOS"+form_data["POSProfile"]
        
        customer = frappe.db.exists('Customer', form_data['Customer']['id'])
        if customer:
            frappe.set_user("Administrator")
            return customer
        
        customer = frappe.get_doc({
            'doctype': 'Customer',
            'customer_name': form_data['Customer']['Name'],
            'customer_group': 'Retail',
            'territory': 'All Territories',
            'first_name': form_data['Customer']['Name'].split(' ')[0],
            'last_name': form_data['Customer']['Name'].split(' ')[1] if len(form_data['Customer']['Name'].split(' ')) > 1 else '',
            'customer_name': form_data['Customer']['Name'],
            'territory': 'All Territories',
            'default_price_list': form_data['PriceList'] if "PriceList" in form_data else "",
            'default_currency': frappe.db.get_value("Price List", form_data['PriceList'], 'currency') if "PriceList" in form_data else "",
            'customer_type': 'Individual'
        })
        
        customer.save(ignore_permissions=True)
        contact = create_contact(form_data, customer)
        
        frappe.db.set_value('Customer', customer.name, 'customer_primary_contact', contact)
        frappe.db.commit()
        
        frappe.set_user("Administrator")
        return customer.name
    except Exception as e:
        frappe.set_user("Administrator")
        frappe.log_error(title='Create Customer Error', message=frappe.get_traceback())
        return None

def create_contact(form_data, customer):
    frappe.set_user(form_data['SalesPerson'])
    try:
        phone = form_data['Customer']['Phone'].replace(' ', '') if form_data['Customer']['Phone'] else ""
        contact_info = {
            'doctype': 'Contact',
            'first_name': form_data['Customer']['Name'].split(' ')[0],
            'last_name': form_data['Customer']['Name'].split(' ')[1] if len(form_data['Customer']['Name'].split(' ')) > 1 else '',
            'email_id': form_data['Customer']['Email'] if form_data['Customer']['Email'] else '',
            'phone': phone,
            'mobile_no': phone
        }
        
        contact_info.update({'links': [{'link_doctype': 'Customer', 'link_name': customer.name}]})
        if phone:
            contact_info.update({'phone_nos': [{'phone': phone, 'is_primary_phone': 1, 'is_primary_mobile_no': 1}]})

        if form_data['Customer']['Email']:
            contact_info.update({'email_ids': [{'email_id': form_data['Customer']['Email'], 'is_primary': 1}]})
        
        contact = frappe.get_doc(contact_info)
        contact.save(ignore_permissions=True)
        frappe.db.commit()
        frappe.set_user("Administrator")
        return contact.name
    except Exception as e:
        frappe.set_user("Administrator")
        frappe.log_error(title='Create Contact Error', message=frappe.get_traceback())
        return None

def get_payments(form_data):
    payments = []
    for payment in form_data['Payment']:
        payments.append({
            'mode_of_payment': payment['ModeOfPayment'],
            'amount': payment['Amount'],
        })
        
    return payments
        
def get_comments(form_data):
    comments = []
    for comment in form_data['Comments']:
        comments.append({
            'comment_by': comment['UserId'] if comment['UserId'] else 'Administrator',
            'comment': comment['Text'] if comment['Text'] else 'No Comment',
        })
        
    return comments