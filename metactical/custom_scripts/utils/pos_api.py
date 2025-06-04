import frappe
from metactical.custom_scripts.sales_order.sales_order import make_sales_invoice
from metactical.custom_scripts.utils.metactical_utils import ( 
	post_to_rocket_chat, queue_action
)
from frappe.utils import file_lock, now_datetime, get_url, flt
from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_sales_return
import json

@frappe.whitelist()
def receive_pos_data(*args, **kwargs):
    form_data = dict(frappe.form_dict)
    order_type = "New Order" if not form_data["InvoiceId"] else "Manual Order"
    log = create_log(form_data, order_type)

    user_validation = validate_users(form_data)
    if not user_validation["success"]:
        frappe.response["Status"] = "500"
        frappe.response["Message"] = [user_validation["error"]]
        frappe.response["InvoiceId"] = None
        frappe.response["Total"] = 0.0
        frappe.db.set_value('POS API Log', log, 'error', user_validation["error"])
        frappe.db.commit()
        return
        
    try:        
        customer = get_customer(form_data)
        if not customer:
            frappe.response["Status"] = "500"
            frappe.response["Message"] = ["Unable to create/find Customer"]
            frappe.response["InvoiceId"] = None
            frappe.response["Total"] = 0.0
            frappe.db.set_value('POS API Log', log, 'error', "Unable to create/find Customer")
            frappe.db.commit()
            return
            
        if form_data["InvoiceId"]:
            sales_order = frappe.get_doc('Sales Order', form_data["InvoiceId"])
            if sales_order.docstatus != 1:
                frappe.response["Status"] = "500"
                frappe.response["Message"] = ["Sales Order {0} is not submitted".format(form_data["InvoiceId"])]
                frappe.response["InvoiceId"] = None
                frappe.response["Total"] = 0.0
                frappe.db.set_value('POS API Log', log, 'error', "Sales Order {0} is not submitted".format(form_data["InvoiceId"]))
                frappe.db.commit()
                return
            
            if sales_order.status != "To Deliver and Bill":
                frappe.response["Status"] = "500"
                frappe.response["Message"] = ["Unable to update Sales Order {0}. The status is {1}".format(form_data["InvoiceId"], sales_order.status)]
                frappe.response["InvoiceId"] = None
                frappe.response["Total"] = 0.0
                frappe.db.set_value('POS API Log', log, 'error', "Unable to update Sales Order {0}. The status is {1}".format(form_data["InvoiceId"], sales_order.status))
                frappe.db.commit()
                return
            
            # update the sales order with the new data
            update_details = update_sales_order(sales_order, form_data)
            if not update_details["success"]:
                frappe.response["Status"] = "500"
                frappe.response["Message"] = [update_details["error"]]
                frappe.response["InvoiceId"] = None
                frappe.response["Total"] = 0.0
                frappe.db.set_value('POS API Log', log, 'error', update_details["error"], update_modified=False)
                frappe.db.commit()
                return
            
            sales_order = frappe.get_doc('Sales Order', form_data["InvoiceId"])
            sales_order = {"sales_order": sales_order}
        else:
            sales_order = create_sales_order(form_data, customer)
            if not sales_order["success"] and not sales_order["sales_order"]:
                frappe.response["Status"] = "500"
                frappe.response["Message"] = [sales_order["error"]]
                frappe.response["InvoiceId"] = None
                frappe.response["Total"] = 0.0
                frappe.db.set_value('POS API Log', log, 'error', sales_order["error"], update_modified=False)
                frappe.db.commit()
                return
                        
            if not sales_order["success"]:
                url = "/app/{0}/{1}".format(sales_order["sales_order"].doctype.lower().replace(" ", "-"), sales_order["sales_order"].name)
                message = "Branch: *{0}* \n Sales Order created by POS has an error: `{1}`. \nPlease update the document and resubmit. [{2}]({3})".format(
                    form_data['POSProfile'], sales_order["error"], get_url(url), get_url(url))
                
                frappe.enqueue(
                    post_to_rocket_chat,
                    queue="default", # one of short, default, long
                    doc=sales_order["sales_order"],
                    msg=message,
                    pos=True
                )
                
                comment = get_so_comment(sales_order["sales_order"], form_data, sales_order["error"])
                comment = {"comment_by": form_data['SalesPerson'], "comment": comment}
                create_comment(comment, form_data['SalesPerson'], sales_order["sales_order"].name)
                
        has_no_error = sales_order["success"]        
        sales_order = sales_order["sales_order"]
        
        if sales_order and has_no_error:
            if len(form_data["Payment"]):
                has_intrac_payment = False
                for payment in form_data["Payment"]:
                    if payment["ModeOfPayment"] == "Interac Etransfer":
                        has_intrac_payment = True
                        break
                    
                if not has_intrac_payment:
                    frappe.enqueue(
                        submit_sales_order,
                        queue="default", # one of short, default, long
                        at_front=True,
                        form_data=form_data,
                        sales_order=sales_order.name,
                        log=log
                    )
                else:
                    add_payment_info_to_sales_order(sales_order, form_data)
                                    
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
        frappe.log_error(title='Receive POS Data Error', message=frappe.get_traceback())
        frappe.db.set_value('POS API Log', log, 'error', str(e), update_modified=False)
        
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
        manager_approver = frappe.db.get_value('User', {'full_name': approver["ManagerId"]}, 'name') if approver["ManagerId"] else None
        cashier_approver = frappe.db.get_value('User', {'full_name': approver["CashierId"]}, 'name') if approver["CashierId"] else None
        
        if not approver["ManagerId"] and not approver["CashierId"]:
            return {"error": "ManagerId or CashierId is required to apply discounts", "success": False}
                    
        discount = 0
        if approver["isOverallDiscount"]:
            discount = form_data['OverallDiscount']
        else:
            for item in form_data['Items']:
                if item['ItemCode'] == approver["ItemId"]:
                    discount = item['Discount']
                    break
                
            if not discount:
                return {"error": "Discount applied for an item {0} that is not in the order".format(approver["ItemId"]), "success": False}
        
        if approver["ManagerId"] and not manager_approver:
            return {"error": "User {0} does not exist".format(approver["ManagerId"]), "success": False}
        if approver["CashierId"] and not cashier_approver:
            return {"error": "User {0} does not exist".format(approver["CashierId"]), "success": False}
        
        if approver["ManagerId"] and manager_approver not in users:
            return {"error": "User {0} is not allowed to approve POS transactions".format(manager_approver), "success": False}
        if approver["CashierId"] and cashier_approver not in users:
            return {"error": "User {0} is not allowed to approve POS transactions".format(cashier_approver), "success": False}
        
        if approver["CashierId"]:
            if users[cashier_approver]["ifw_max_discount_percent"] < discount and not manager_approver:
                return {"error": "User {0} is not allowed to give POS discount greater than {1}%".format(cashier_approver, users[cashier_approver]["ifw_max_discount_percent"]), "success": False}

        if manager_approver:
            if not users[manager_approver]["ifw_is_main_pos_user"]:
                return {"error": "User {0} is not allowed to approve Discounts in POS transactions for {1} profile".format(manager_approver, pos_profile), "success": False}
            if users[manager_approver]["ifw_max_discount_percent"] < discount:
                return {"error": "User {0} is not allowed to approve POS transactions with discount greater than {1}%".format(manager_approver, users[manager_approver]["ifw_max_discount_percent"]), "success": False}
                
    return {"success": True}
                
                   
def create_sales_order(form_data, customer):
    items = form_data['Items']
    taxes = form_data['Taxes']
    company = frappe.db.get_value("POS Profile", form_data['POSProfile'] + ' Operators', ['company_address', "company"], as_dict=True)
    if not company:
        return {"success": False, "error": "Company Address not found for {0}".format(form_data['POSProfile'] + ' Operators')}
    
    so_data = {
        'doctype': 'Sales Order',
        'customer': customer,
        'taxes_and_charges': form_data['TaxesAndChargesTemplate'],
        'delivery_date': frappe.utils.today(),
        "company": company.company,
        'company_address': company.company_address,
        'source': form_data['LeadSource'],
        'ignore_pricing_rule': 1,
        'contact_person': frappe.db.get_value('Customer', customer, 'customer_primary_contact'),
        'additional_discount_percentage': form_data['OverallDiscount'],
        "owner": form_data['SalesPerson'],
    }
        
    items = get_items(form_data)
    so_data.update({'items': items})
    
    taxes = get_taxes(form_data, company.company)
    so_data.update({'taxes': taxes})
        
    frappe.set_user(form_data['SalesPerson'])
    sales_order = frappe.get_doc(so_data)
    
    check_coupon_code(sales_order, form_data)

    try:
        sales_order.insert(ignore_permissions=True)
    except Exception as e:
        frappe.clear_last_message()
        
        so_data['items'] = [{
            'item_code': 2,
            'qty': 1,
            'rate': form_data['Total'], 
        }]
        
        so_data['taxes'] = []
        so_data["coupon_code"] = sales_order.coupon_code if hasattr(sales_order, 'coupon_code') else None
        sales_order = frappe.get_doc(so_data)
        
        sales_order.insert(ignore_permissions=True)
        frappe.set_user("Administrator")
        frappe.db.commit()
        
        if sales_order.items:
            item = sales_order.items[0].name
            frappe.delete_doc('Sales Order Item', item)
            
        return {"success": False, "error": str(e), "sales_order": sales_order}

    frappe.set_user("Administrator")
    frappe.db.commit()    
    return {"success": True, "sales_order": sales_order, "error": ""}

def check_coupon_code(sales_order, form_data):
    for payment in form_data['Payment']:
        if payment['ModeOfPayment'] == "Gift Card" and not payment['CouponCode']:
            frappe.throw("Coupon Code is required for Gift Card payment")
            
        if payment['ModeOfPayment'] == "Gift Card" and payment['CouponCode']:
            coupon_code = frappe.db.exists("Coupon Code", {"coupon_code": payment['CouponCode'], "used": 0})
            sql = get_coupon_code_sql(coupon_code)
            gift_card = frappe.db.sql(sql, as_dict=True)
                        
            if gift_card:
                coupon_code = gift_card[0]
                if coupon_code["discount_amount"] == payment['Amount']:
                    sales_order.coupon_code = coupon_code["coupon_name"]
                    continue
                else:
                    if coupon_code["discount_amount"] > payment['Amount']:
                        doc = frappe._dict({
                            "name": coupon_code["custom_sales_invoice"],
                            "grand_total": -1*payment['Amount'],
                            "customer": sales_order.customer
                        })
                            
                        new_gift_card = create_gift_card(doc, form_data, coupon_code["coupon_name"])
                        remaining_amount = coupon_code["discount_amount"] - payment['Amount']
                        
                        frappe.db.set_value('Pricing Rule', coupon_code.pricing_rule, 'discount_amount', remaining_amount)
                        frappe.db.commit()
                        
                        if form_data["InvoiceId"]:
                            frappe.db.set_value('Sales Order', sales_order.name, 'coupon_code', new_gift_card.name)
                        else:
                            sales_order.coupon_code = new_gift_card.name
                    else:
                        frappe.throw("Coupon Code {0} has a discount amount of {1} which is less than the payment amount of {2}".format(coupon_code.coupon_code, coupon_code.discount_amount, payment['Amount']))
            else:
                frappe.throw("Coupon Code {0} is not valid".format(payment['CouponCode']))
                        
def update_sales_order(sales_order, form_data):
    items = get_items(form_data)
        
    try:
        # add sales order id
        i = 0
        for item in items:
            found = False
            for sales_item in sales_order.items:
                if (item['item_code'] == 2 and sales_item.item_name == item['item_name']) or (item['item_code'] == sales_item.item_code and item["item_code"] != 2):
                    item["name"] = sales_item.name
                    item["docname"] = sales_item.name
                    item["idx"] = i + 1
                    found = True
                    
            if not found:
                item["__islocal"] = True
                item["idx"] = i + 1
                item["name"] = "Row-{0}".format(i + 1)
                
            i += 1
        parent_doctype = sales_order.doctype
        parent_doctype_name = sales_order.name
        child_docname = "items"
            
        from metactical.custom_scripts.controllers.accounts_controller import update_child_qty_rate
        
        trans_items = json.dumps(items)
        
        update_child_qty_rate(parent_doctype, trans_items, parent_doctype_name, child_docname)
        check_coupon_code(sales_order, form_data)
        frappe.db.commit()
        return {"success": True, "message": ""}
    except Exception as e:
        return {"success": False, "error": str(e)}

def submit_sales_order(sales_order, form_data, log):
    frappe.set_user(form_data["SalesPerson"])
    try:
        frappe.db.set_value('POS API Log', log, 'sales_order', sales_order, update_modified=False)
        sales_order = frappe.get_doc('Sales Order', sales_order)
        if sales_order.docstatus == 0:
            sales_order.submit()    
            frappe.db.commit()    
    except Exception as e:
        frappe.set_user("Administrator")
        frappe.log_error(title='Submit Sales Order Error', message=frappe.get_traceback())
        frappe.db.set_value('POS API Log', log, 'error', str(e), update_modified=False)
        
        if type(sales_order) == str:
            sales_order = frappe.get_doc('Sales Order', sales_order)
        
        # add comment to sales order
        comment = {"comment_by": form_data['SalesPerson'], "comment": str(e)}    
        create_comment(comment, form_data['SalesPerson'], sales_order.name)
        
        url = "/app/{0}/{1}".format(sales_order.doctype.lower().replace(" ", "-"), sales_order.name)
        message = "Branch: *{0}* \n Unable to submit Sales Order created by POS. Please check the document and resubmit. \n[{1}]({2})".format(form_data['POSProfile'], get_url(url), get_url(url))
        post_to_rocket_chat(sales_order, message, pos=True)
        
        add_payment_info_to_sales_order(sales_order, form_data)

        return
    
    sales_invoice = None
    try:
        sales_invoice = create_invoice(sales_order, form_data)
        frappe.db.set_value('POS API Log', log, 'sales_invoice', sales_invoice.name)
        frappe.db.commit()
    except Exception as e:
        frappe.set_user("Administrator")
        frappe.log_error(title='Create Invoice Error', message=frappe.get_traceback())
        frappe.db.set_value('POS API Log', log, 'error', str(e), update_modified=False)
        
        # add comment to sales order
        comment = {"comment_by": form_data['SalesPerson'], "comment": str(e)}
        create_comment(comment, form_data['SalesPerson'], sales_order.name)
        
        # post to rocket chat
        url = "/app/{0}/{1}".format(sales_order.doctype.lower().replace(" ", "-"), sales_order.name)
        message = "Branch: *{0}* \n Unable to create Invoice for Sales Order created by POS. Please check the document and resubmit. \n[{1}]({2})".format(form_data['POSProfile'], get_url(url), get_url(url))
        # message = "Unable to create Invoice for Sales Order created by POS. Please check the document and resubmit. \n[{0}]({1})".format(get_url(url), get_url(url))
        post_to_rocket_chat(sales_order, message, pos=True)
        
        # add payment info to sales order
        add_payment_info_to_sales_order(sales_order, form_data)

        return
    
    if sales_invoice:
        try:
            frappe.db.commit()
            sales_invoice.submit()
            frappe.db.commit()
        except Exception as e:
            frappe.db.rollback()
            frappe.set_user("Administrator")
            frappe.log_error(title='Submit Invoice Error', message=frappe.get_traceback())
            frappe.db.set_value('POS API Log', log, 'error', str(e), update_modified=False)
            
            # add comment to sales order
            comment = {"comment_by": form_data['SalesPerson'], "comment": str(e)}
            create_comment(comment, form_data['SalesPerson'], sales_invoice.name, "Sales Invoice")
            
            # post to rocket chat
            url = "/app/{0}/{1}".format(sales_invoice.doctype.lower().replace(" ", "-"), sales_invoice.name)
            # message = "Unable to submit Invoice created by POS. Please check the document and resubmit. \n[{0}]({1})".format(get_url(url), get_url(url))
            message = "Branch: *{0}* \n Unable to submit Invoice created by POS. Please check the document and resubmit. \n[{1}]({2})".format(form_data['POSProfile'], get_url(url), get_url(url))
            post_to_rocket_chat(sales_invoice, message, pos=True)
            
            # add payment info to sales order
            add_payment_info_to_sales_order(sales_order, form_data)
            
        # queue_action(sales_invoice, 'submit')
        frappe.set_user("Administrator")

def add_payment_info_to_sales_order(sales_order, form_data):
    if "Payment" not in form_data:
        return
    
    message = ""
    for payment in form_data['Payment']:
        if payment['ModeOfPayment'] == "Interac Etransfer":
            message += "Payment of <b>$ {0}</b> will be made via <b>{1}</b> <br>".format(payment['Amount'], payment['ModeOfPayment'])
        else:
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
    
def create_comment(comment, commentor, sales_order, doctype="Sales Order"):
    if comment:
        frappe.get_doc({
            'doctype': 'Comment',
            'comment_email': commentor,
            'comment_by': comment['comment_by'],
            'content': comment['comment'],
            'reference_doctype': doctype,
            "comment_type": "Comment",
            'reference_name': sales_order,
        }).save(ignore_permissions=True)
        frappe.db.commit()
    
def create_invoice(sales_order, form_data):
    sales_invoice = make_sales_invoice(sales_order.name)
    sales_invoice.is_pos = 1
    sales_invoice.update_stock = 1
    sales_invoice.write_off_outstanding_amount_automatically = 0
    sales_invoice.pos_profile = form_data['POSProfile'] + ' Operators'
    frappe.set_user(form_data['SalesPerson'])
    payments = get_payments(form_data)
    sales_invoice.update({'payments': payments})
    sales_invoice.save()
    
    # add a write off amount when there is a difference between the total and the payment amount 
    if sales_invoice.grand_total != form_data['Total']:		
        net_paid_amount_form = get_total_paid_with_change(form_data)
        net_paid_erpnext = sales_invoice.paid_amount - sales_invoice.change_amount
        difference = sales_invoice.grand_total - form_data['Total']

        if not(net_paid_amount_form != net_paid_erpnext and difference < 0):
            write_off_limit = flt(frappe.db.get_value("POS Profile", sales_invoice.pos_profile, "write_off_limit"))
            
            if write_off_limit and difference <= write_off_limit:
                sales_invoice.write_off_amount = difference
                sales_invoice.change_amount = .10
                sales_invoice.save()
                frappe.db.commit()

    frappe.set_user("Administrator")
    return sales_invoice

def get_total_paid_with_change(form_data):
    total_paid = 0.0
    for payment in form_data['Payment']:
        if payment['ModeOfPayment'] == "Cash":
            total_paid += payment['Amount'] - payment['Change']
        else:
            total_paid += payment['Amount']
            
    return total_paid
    
def get_taxes(form_data, company):  
    taxes = []
    # company = frappe.db.get_single_value('Global Defaults', 'default_company')
    company_abr = frappe.db.get_value('Company', company, 'abbr')
    
    for tax in form_data['Taxes']:
        taxes.append({
            'charge_type': 'On Net Total',
            'account_head': tax['TaxId'].split(" ")[0] + " - " + company_abr,
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
            'rate': rate - (item['Rate'] * (item['Discount'] / 100)),
            'qty': qty,
            'discount_percentage': item['Discount'],
            'warehouse': item["Warehouse"] if "Warehouse" in item else warehouse,
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

def get_so_comment(sales_order, form_data, error=None):   
    comment = "<b>Error</b>: <span class='text-danger'>{0}</span><br><br>".format(error) if error else ""
    # add items to the comment
    if form_data['Items']:
        comment += "<table class='table'><thead><th>Item Code</th><th>Item Name</th><th>Qty</th><th>Rate</th><th>Discount</th></thead><tbody>"
        for item in form_data['Items']:
            comment += "<tr><td>{0}</td><td>{1}</td><td>{2}</td><td>{3}</td><td>{4}%</td></tr>".format(
                item['ItemCode'], item['ItemName'], item['Qty'], item['Rate'], item['Discount'])
        comment += "</tbody></table>"
    else:
        comment += "<br>*No Items*"
        
    # add payment info to the comment
    if form_data['Payment']:
        coupon_code = ""
        comment += "<br><b>Payments:</b> "
        for payment in form_data['Payment']:
            comment += "<br>{0} - $ {1}".format(payment['ModeOfPayment'], payment['Amount'])
            if payment['ModeOfPayment'] == "Gift Card" and payment['CouponCode']:
                coupon_code = payment['CouponCode']
                comment += " (Coupon Code: {0})".format(coupon_code)
    else:
        comment += "<br>*No Payments*"
        
    # add taxes to the comment
    if form_data['Taxes']:
        comment += "<br><br><b>Taxes</b>"
        for tax in form_data['Taxes']:
            comment += "<br>{0} - {1}%".format(tax['TaxId'], tax['Amount'])
    else:
        comment += "<br>*No Taxes*"
        
    # add total to the comment
    if form_data['Total']:
        comment += "<br><br><b>Total:</b> $ {0}".format(form_data['Total'])
    else:
        comment += "<br>*No Total*"
        
    comment += "<br><br><b>Branch</b>: {0}".format(form_data['POSProfile'])
    # add customer info to the comment
    if form_data['Customer'] and form_data['Customer']['Name']:
        comment += "<br><b>Customer:</b> {0} ({1}) - {2}".format(form_data['Customer']['Name'], form_data['Customer']['Phone'], form_data['Customer']['Email'])
    else:
        comment += "<br>*No Customer*"
        
        # add overall discount to the comment
    if form_data['OverallDiscount']:
        comment += "<br><br><b>Overall Discount:</b> {0}%".format(form_data['OverallDiscount'])
    else:
        comment += "<br>*No Overall Discount*"
        
    return comment    

@frappe.whitelist()
def get_item_from_barcode(barcode, branch):
    item = frappe.db.sql(f"""
        SELECT 
            tabItem.name, item_name, ifw_retailskusuffix,
            brand, image, is_stock_item
        FROM `tabItem Barcode` ib Join `tabItem` on ib.parent=tabItem.name
        WHERE 
            `tabItem`.disabled = 0
            and `tabItem`.is_sales_item = 1
            and ib.barcode = {frappe.db.escape(barcode)}
        limit 1
    """, as_dict=True)    

    pos_profile = branch + ' Operators'    
    pos_profile = frappe.get_doc('POS Profile', pos_profile)
    company = pos_profile.company
    price_list = pos_profile.selling_price_list
    warehouse = pos_profile.warehouse

    if item:
        item = item[0]    
        frappe.response["Sku"] = item.name
        frappe.response["ItemName"] = item.item_name
        frappe.response["RetailSku"] = item.ifw_retailskusuffix
        frappe.response["Categories"] = []
        frappe.response["Comment"] = ""
        frappe.response["ImageUrl"] = item.image if item.image else ""
        frappe.response["Brand"] = item.brand if item.brand else ""
        frappe.response["NonStocking"] = False if item.is_stock_item else True
        barcodes = frappe.db.get_all("Item Barcode", {"parent": item.name}, ["barcode"])
        frappe.response["Barcodes"] = [{"Barcode": barcode.barcode} for barcode in barcodes]
        frappe.response["Quantity"] = int(get_quantity(item.name, warehouse))
        
        item_price = get_item_price(item.name, price_list)
        frappe.response["Price"] = item_price
        
        discount = get_item_discount(item.name, price_list, item_price, company)
        frappe.response["DiscountPrice"] = discount["discount_price"] if discount else item_price
        frappe.response["OnSale"] = discount["on_sale"] if discount else False
        frappe.response["DiscountExpiryDate"] = discount["discount_expiry_date"] if discount else None
        frappe.response["DiscountStartDate"] = discount["discount_start_date"] if discount else None

def get_quantity(item, warehouse):
    bin_qty = frappe.db.get_value('Bin', {'item_code': item, 'warehouse': warehouse}, ['actual_qty', 'reserved_qty'])
    quantity = 0
    if bin_qty:
        quantity = bin_qty[0] - bin_qty[1]
        
    return quantity
        
def get_item_price(item, price_list):
    price = frappe.db.get_value('Item Price', {'item_code': item, 'price_list': price_list}, ['price_list_rate'])
    if not price:
        return 0.0
    
    return price

def get_item_discount(item, price_list, item_price, company):
    # select all pricing rules for the item and pick the one with the highest priority for each item
    pricing_rule = frappe.db.sql(f"""
        SELECT
            valid_from AS discount_start_date,
            valid_upto AS discount_expiry_date,
            disable AS on_sale,
            discount_percentage, rate, rate_or_discount, discount_amount
        FROM
            `tabPricing Rule Item Code`
        JOIN
            `tabPricing Rule` ON `tabPricing Rule`.name = `tabPricing Rule Item Code`.parent
        WHERE
            `tabPricing Rule Item Code`.item_code = '{item}'
            AND (`tabPricing Rule`.for_price_list = '{price_list}' or `tabPricing Rule`.for_price_list is NULL)
            AND `tabPricing Rule`.disable = 0
            AND `tabPricing Rule`.valid_upto >= CURDATE()
            AND `tabPricing Rule`.company = '{company}'
        ORDER BY
            CAST(`tabPricing Rule`.priority AS UNSIGNED) DESC
        LIMIT 1;
    """, as_dict=1)

    if pricing_rule:
        if pricing_rule[0].rate_or_discount == "Discount Percentage":
            discount_price =  item_price - (item_price * pricing_rule[0].discount_percentage / 100)
        elif pricing_rule[0].rate_or_discount == "Discount Amount":
            discount_price = item_price - pricing_rule[0].discount_amount
        else:
            discount_price = pricing_rule[0].rate
            
        return {
            "discount_start_date": pricing_rule[0].discount_start_date,
            "discount_expiry_date": pricing_rule[0].discount_expiry_date,
            "on_sale": not pricing_rule[0].on_sale,
            "discount_price": discount_price
        }
    else:
        return {}
    
@frappe.whitelist()
def create_return(*args, **kwargs):
    form_data = dict(frappe.form_dict)
    try:
        frappe.set_user(form_data['SalesPerson'])
        log = create_log(form_data, 'Sales Return')
        
        # Check if SalesPerson exists
        if "SalesPerson" not in form_data or not form_data["SalesPerson"]:
            frappe.response["Message"] = "Sales Person is required"
            frappe.response["Status"] = 500
            frappe.response["CouponCode"] = None
            return
        else:
            if not frappe.db.exists('User', form_data['SalesPerson']):
                frappe.response["Message"] = "User {0} does not exist".format(form_data['SalesPerson'])
                frappe.response["Status"] = 500
                frappe.response["CouponCode"] = None
                return
                
        invoiceId = form_data["InvoiceId"]
        sales_return = make_sales_return(invoiceId)
        formatted_items = get_items(form_data)
        items = sales_return.items.copy()
        filtered_items = []

        for item in items:
            for updated_item in formatted_items:
                if ((item.item_code == updated_item["item_code"] and updated_item["qty"] != 0 and updated_item["item_code"] != "2") or 
                    (updated_item["item_code"] == "2" and item.item_name == updated_item["item_name"] and updated_item["qty"] != 0)):
                    item.qty = (-1 * updated_item["qty"]) if updated_item["qty"] > 0 else updated_item["qty"]
                    item.price_list_rate = updated_item["price_list_rate"] if updated_item["qty"] > 0 else updated_item["price_list_rate"]
                    item.discount_percentage = updated_item["discount_percentage"] if updated_item["qty"] > 0 else updated_item["discount_percentage"]
                    item.discount_amount = item.price_list_rate * (item.discount_percentage / 100)
                    item.margin_type = ""
                    item.rate = item.price_list_rate - item.discount_amount
                    filtered_items.append(item)

        sales_return.items = filtered_items
        # sales_return.additional_discount_percentage = form_data['OverallDiscount']
        sales_return.calculate_taxes_and_totals()
        
        total_payment = sum(payment.amount for payment in sales_return.payments)
        invoice_total = sales_return.rounded_total or sales_return.grand_total
        
        if float(total_payment) + float(sales_return.write_off_amount) != float(invoice_total) and sales_return.payments:
            difference = round(float(invoice_total) - float(total_payment) + float(sales_return.write_off_amount), 2)
            sales_return.payments[0].amount = total_payment + difference
    
        sales_return.save()
        sales_return.submit()
        frappe.db.set_value('POS API Log', log, 'sales_return', sales_return.name, update_modified=False)
    except Exception as e:
        frappe.db.rollback()
        frappe.clear_last_message()
        frappe.set_user("Administrator")
        
        frappe.log_error(title='Submit Sales Return Error', message=frappe.get_traceback())
        frappe.db.set_value('POS API Log', log, 'error', str(e), update_modified=False)
        
        frappe.response["Status"] = 500
        frappe.response["Message"] = str(e)
        frappe.response["CouponCode"] = None
        return
    
    gift_card = None
    try:
        gift_card = create_gift_card(sales_return, form_data)
        frappe.db.set_value('POS API Log', log, 'coupon_code', gift_card.coupon_code, update_modified=False)
    except Exception as e:
        frappe.clear_last_message()
        frappe.set_user("Administrator")
        
        frappe.log_error(title='Create Gift Card Error', message=frappe.get_traceback())
        frappe.db.set_value('POS API Log', log, 'error', str(e), update_modified=False)
        
        frappe.response["Status"] = 500
        frappe.response["Message"] = str(e)
    
    frappe.response["Status"] = 200
    frappe.response["Message"] = ""
    frappe.response["CouponCode"] = gift_card.coupon_code if gift_card else None
    frappe.response["SalesReturn"] = sales_return.name
    frappe.response["Total"] = sales_return.grand_total
    frappe.db.commit()
    
def create_gift_card(doc, form_data, coupon_code=None):
    # create pricing rule for the gift card
    try:
        frappe.set_user(form_data['SalesPerson'])
        pricing_rule = get_or_create_pricing_rule(doc)
        
        existing_coupon_codes = frappe.db.count("Coupon Code", {"customer": doc.customer})
        description = ""
        if coupon_code:
            description = "Gift Card from Coupon code <a href='/app/coupon-code/{0}'>{1}</a> for {2} from {3}".format(coupon_code, coupon_code, doc.customer, doc.name)
        
        # create gift card item
        gift_card = frappe.get_doc({
            "doctype": "Coupon Code",
            "coupon_name": doc.customer +"-"+str((existing_coupon_codes + 1)),
            "coupon_type": "Gift Card",
            "customer": doc.customer,
            "pricing_rule": pricing_rule,
            "valid_from": now_datetime(),
            "custom_sales_invoice": doc.name,
            "description": description,
            "used": 1 if form_data["InvoiceId"] and form_data["InvoiceId"].startswith("SAL-ORD") else 0
        })
        
        gift_card.insert(ignore_permissions=True)
        gift_card.save()
        frappe.db.commit()
        frappe.set_user("Administrator")
        
        return gift_card
    except Exception as e:
        frappe.throw("Unable to create Gift Card: {0}".format(str(e)))

def get_or_create_pricing_rule(doc):
    pricing_rule = frappe.get_doc({
            "title": "GC-{0}".format(doc.customer),
            "doctype": "Pricing Rule",
            "coupon_code_based": 1,
            "apply_on": "Transaction",
            "price_or_product_discount": "Price",
            "selling": 1,
            "valid_from": now_datetime(),
            "rate_or_discount": "Discount Amount",
            "discount_amount": -1 * doc.grand_total
        })
    
    pricing_rule.insert(ignore_permissions=True)
    frappe.db.commit()
    return pricing_rule.name
    
    return pricing_rule    

def create_log(form_data, request_type):
    try:
        log = frappe.get_doc({
            'doctype': 'POS API Log',
            'request_type': request_type,
            'payload': json.dumps(form_data),
        })
        log.insert(ignore_permissions=True)
        frappe.db.commit()
        return log.name
    except Exception as e:
        frappe.log_error(title='POS API Log Error', message=frappe.get_traceback())
        
@frappe.whitelist()
def verify_coupon_code(coupon_code):
    if not coupon_code:
        frappe.response["Status"] = 500
        frappe.response["Message"] = "Coupon Code is required"
        frappe.response["Amount"] = 0.0
        return
    
    coupon_code = frappe.db.exists("Coupon Code", {"coupon_code": coupon_code, "used": 0})
    if not coupon_code:
        frappe.response["Status"] = 500
        frappe.response["Message"] = "Coupon Code is not valid"
        frappe.response["Amount"] = 0.0
        return
    
    sql = get_coupon_code_sql(coupon_code)
    coupon_code = frappe.db.sql(sql, as_dict=True)

    if not coupon_code:
        frappe.response["Status"] = 500
        frappe.response["Message"] = "Coupon Code is not valid"
        frappe.response["Amount"] = 0.0
        return
    
    coupon_code = coupon_code[0]
    frappe.response["Status"] = 200
    frappe.response["Message"] = ""
    frappe.response["CouponCode"] = coupon_code.coupon_code
    frappe.response["Amount"] = coupon_code.discount_amount
    frappe.response["Customer"] = coupon_code.customer
    
def get_coupon_code_sql(coupon_code):
    return f"""
        SELECT
            coupon_code, coupon_name, cc.customer, coupon_type, custom_sales_invoice,
            cc.valid_from, cc.valid_upto, pr.discount_amount, pricing_rule
        FROM
            `tabCoupon Code` cc
        JOIN
            `tabPricing Rule` pr ON cc.pricing_rule = pr.name
        JOIN 
            `tabSales Invoice` si ON cc.custom_sales_invoice = si.name
        WHERE
            cc.name = {frappe.db.escape(coupon_code)}
            AND used = 0
            AND (cc.valid_upto >= CURDATE() or cc.valid_upto is NULL)
            AND cc.valid_from <= CURDATE()
            AND pr.disable = 0
            AND si.docstatus = 1
    """
    
@frappe.whitelist()
def get_item_by_retail_sku(retail_sku, branch, page_size=10, page=1):
    page = int(page or 1)
    limit = int(page_size or 10)
    offset = (page - 1) * limit

    # Fetch matching items
    items = frappe.db.sql(f"""
        SELECT
            tabItem.name AS item_code, item_name, ifw_retailskusuffix,
            variant_of,
            brand, image, is_stock_item, tabItem.has_variants,
            (
                SELECT GROUP_CONCAT(barcode SEPARATOR ', ')
                FROM `tabItem Barcode`
                WHERE parent = tabItem.name
            ) AS barcodes
        FROM `tabItem`
        WHERE
            tabItem.disabled = 0
            AND tabItem.is_sales_item = 1
            AND tabItem.has_variants = 0
            AND tabItem.ifw_retailskusuffix LIKE {frappe.db.escape(f"{retail_sku}%")}
        LIMIT {limit} OFFSET {offset}
    """, as_dict=True)

    if not items:
        frappe.response.update({
            "Status": 404,
            "Message": "Item not found",
            "Items": []
        })
        return

    # Fetch POS profiles
    pos_profiles = frappe.get_all("POS Profile", fields=["company", "selling_price_list", "warehouse", "name"], filters={"disabled": 0})
    
    # Group POS profiles by selling price list and warehouse
    price_list_map = {}
    warehouse_map = {}
    profile_map = {}

    for profile in pos_profiles:
        profile_map[profile.name] = profile

        price_list_map.setdefault(profile.selling_price_list, []).append(profile.name)
        warehouse_map.setdefault(profile.warehouse, []).append(profile.name)

    all_warehouses = list(warehouse_map.keys())
    all_price_lists = list(price_list_map.keys())

    # Attach inventory and pricing data
    for item in items:
        item.branches = {}

        # Stock quantities per warehouse
        bins = frappe.db.get_all("Bin", filters={
            "item_code": item.item_code,
            "warehouse": ["in", all_warehouses]
        }, fields=["actual_qty", "reserved_qty", "warehouse"], order_by="warehouse")

        for bin in bins:
            for operator in warehouse_map.get(bin.warehouse, []):
                item.branches.setdefault(operator, {
                    "Price": 0.0,
                    "PriceList": "",
                    "Qty": 0,
                    "Branch": operator,
                    "Warehouse": bin.warehouse
                })
                item.branches[operator]["Qty"] = int(bin.actual_qty - bin.reserved_qty)

        # Prices per price list
        prices = frappe.db.get_all("Item Price", filters={
            "item_code": item.item_code,
            "price_list": ["in", all_price_lists]
        }, fields=["price_list", "price_list_rate"])

        for price in prices:
            for operator in price_list_map.get(price.price_list, []):
                branch_info = item.branches.setdefault(operator, {
                    "Qty": 0,
                    "Price": 0.0,
                    "Branch": operator,
                    "Warehouse": profile_map.get(operator, {}).get("warehouse", ""),
                    "PriceList": price.price_list
                })
                branch_info["Price"] = price.price_list_rate or 0.0
                branch_info["PriceList"] = price.price_list or ""

        operator_key = f"{branch} Operators"
        item.qty = item.branches.get(operator_key, {}).get("Qty", 0)
        item.price = item.branches.get(operator_key, {}).get("Price", 0.0)
        item.price_list = item.branches.get(operator_key, {}).get("PriceList", "")
        item.company = profile_map.get(operator_key, {}).get("company", "")

    # Structure final response
    item_details = []

    for item in items:
        barcodes = [{"Barcode": code} for code in item.barcodes.split(", ")] if item.barcodes else []
        discount = {}

        if item.price and item.price_list and item.company:
            discount = get_item_discount(item.item_code, item.price_list, item.price, item.company) or {}

        item_details.append({
            "Sku": item.item_code,
            "ItemName": item.item_name,
            "RetailSku": item.ifw_retailskusuffix,
            "Categories": [],
            "Comment": "",
            "TemplateId": item.variant_of or "",
            "ImageUrl": item.image or "",
            "Brand": item.brand or "",
            "NonStocking": not item.is_stock_item,
            "Barcodes": barcodes,
            "Quantity": item.qty,
            "Price": item.price,
            "DiscountPrice": round(discount.get("discount_price", item.price), 2),
            "OnSale": discount.get("on_sale", False),
            "DiscountExpiryDate": discount.get("discount_expiry_date"),
            "DiscountStartDate": discount.get("discount_start_date"),
            "Branches": list(item.branches.values())
        })

    frappe.response.update({
        "Status": 200,
        "Message": "",
        "Items": item_details
    })


@frappe.whitelist()
def get_item_by_retail_sku_single(retail_sku, branch):
    item = frappe.db.sql(f"""
        SELECT 
            tabItem.name, item_name, ifw_retailskusuffix,
            brand, image, is_stock_item
        FROM `tabItem`
        WHERE 
            `tabItem`.disabled = 0
            and `tabItem`.has_variants = 0
            and `tabItem`.is_sales_item = 1
            and ifw_retailskusuffix = {frappe.db.escape(retail_sku)}
        limit 1
    """, as_dict=True)    

    pos_profile = branch + ' Operators'    
    pos_profile = frappe.get_doc('POS Profile', pos_profile)
    company = pos_profile.company
    price_list = pos_profile.selling_price_list
    warehouse = pos_profile.warehouse

    if item:
        item = item[0]    
        frappe.response["Sku"] = item.name
        frappe.response["ItemName"] = item.item_name
        frappe.response["RetailSku"] = item.ifw_retailskusuffix
        frappe.response["Categories"] = []
        frappe.response["Comment"] = ""
        frappe.response["ImageUrl"] = item.image if item.image else ""
        frappe.response["Brand"] = item.brand if item.brand else ""
        frappe.response["NonStocking"] = False if item.is_stock_item else True
        barcodes = frappe.db.get_all("Item Barcode", {"parent": item.name}, ["barcode"])
        frappe.response["Barcodes"] = [{"Barcode": barcode.barcode} for barcode in barcodes]
        frappe.response["Quantity"] = int(get_quantity(item.name, warehouse))
        
        item_price = get_item_price(item.name, price_list)
        frappe.response["Price"] = item_price
        
        discount = get_item_discount(item.name, price_list, item_price, company)
        frappe.response["DiscountPrice"] = discount["discount_price"] if discount else item_price
        frappe.response["OnSale"] = discount["on_sale"] if discount else False
        frappe.response["DiscountExpiryDate"] = discount["discount_expiry_date"] if discount else None
        frappe.response["DiscountStartDate"] = discount["discount_start_date"] if discount else None