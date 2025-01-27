import frappe
from metactical.custom_scripts.sales_order.sales_order import make_sales_invoice

@frappe.whitelist(allow_guest=True)
def receive_pos_data(*args, **kwargs):
    form_data = frappe.form_dict
    try:        
        # Do something with the data
        customer = get_customer(form_data)
        sales_order = create_sales_order(form_data, customer)
        
        if sales_order:
            frappe.enqueue(
                submit_sales_order,
                queue="default", # one of short, default, long
                is_async=True, # if this is True, method is run in worker
                now=True, # if this is True, method is run directly (not in a worker) 
                job_name=None, # specify a job name
                at_front=True, # put the job at the front of the queue
                form_data=form_data,
                sales_order=sales_order
            )
                    
        frappe.response["status"] = 200
        frappe.response["sales_order"] = sales_order
    
    except Exception as e:
        frappe.log_error(title="pos_data", message=form_data)
        frappe.log_error(title='Receive POS Data Error', message=frappe.get_traceback())
        frappe.response["status"] = 500
        frappe.response["error"] = str(e)
           
def create_sales_order(form_data, customer):
    items = form_data['Items']
    taxes = form_data['Taxes']
    payment = form_data['Payment']
    
    so_data = {
        'doctype': 'Sales Order',
        'customer': customer,
        'taxes_and_charges': form_data['TaxesAndChargesTemplate'],
        'delivery_date': frappe.utils.today(),
        'source': form_data['LeadSource'],
    }
    
    items = get_items(form_data)
    so_data.update({'items': items})
    
    taxes = get_taxes(form_data)
    so_data.update({'taxes': taxes})
    
    sales_order = frappe.get_doc(so_data)
    sales_order.insert()
    frappe.db.commit()
        
    return sales_order.name

def submit_sales_order(sales_order, form_data):
    try:
        sales_order = frappe.get_doc('Sales Order', sales_order)
        sales_order.submit()    
        frappe.db.commit()    
    except Exception as e:
        frappe.log_error(title='Submit Sales Order Error', message=frappe.get_traceback())
        comments = get_comments(form_data)
        for comment in comments:
            frappe.get_doc({
                'doctype': 'Comment',
                'comment_by': comment['UserId'],
                'comment': comment['Text'],
                'reference_doctype': 'Sales Order',
                'reference_name': sales_order.name,
            }).insert()
        return str(e)
    
    sales_invoice = None
    try:
        sales_invoice = create_invoice(sales_order, form_data)
        frappe.db.commit()
    except Exception as e:
        frappe.log_error(title='Create Invoice Error', message=frappe.get_traceback())
        comments = get_comments(form_data)
        for comment in comments:
            frappe.get_doc({
                'doctype': 'Comment',
                'comment_by': comment['UserId'],
                'comment': comment['Text'],
                'reference_doctype': 'Sales Order',
                'reference_name': sales_order.name,
            }).insert()
        return str(e)
        
    try:
        sales_invoice.submit()
    except Exception as e:
        frappe.log_error(title='Submit Invoice Error', message=frappe.get_traceback())
        comments = get_comments(form_data)
        for comment in comments:
            frappe.get_doc({
                'doctype': 'Comment',
                'comment_by': comment['UserId'],
                'comment': comment['Text'],
                'reference_doctype': 'Sales Invoice',
                'reference_name': sales_invoice.name,
            }).insert()
        return str(e)
    
def create_invoice(sales_order, form_data):
    sales_invoice = make_sales_invoice(sales_order.name)
    sales_invoice.is_pos = 1
    sales_invoice.pos_profile = form_data['POSProfile'] + ' Operators'
    payments = get_payments(form_data)
    sales_invoice.update({'payments': payments})
    sales_invoice.save()
    
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
    for item in form_data['Items']:
        item_code = item['ItemCode']
        rate = item['Rate']
        qty = item['Qty']
        
        items.append({
            'item_code': item_code,
            'rate': rate,
            'qty': qty,
            'warehouse': 'W01-WHS-Active Stock - ICL',
        })
        
    return items
    
def get_customer(form_data):
    if not form_data['Customer']['Name']:
        return "DefaultPOS"+form_data["POSProfile"]
    
    customer = frappe.db.exists('Customer', form_data['Customer']['id'])
    if customer:
        return customer
    
    customer = frappe.get_doc({
        'doctype': 'Customer',
        'customer_name': form_data['Customer']['Name'],
        'customer_group': 'Retail',
        'territory': 'All Territories',
        'first_name': form_data['Customer']['Name'].split(' ')[0],
        'last_name': form_data['Customer']['Name'].split(' ')[1],
        'customer_name': form_data['Customer']['Name'],
        'territory': 'All Territories',
        'default_price_list': form_data['PriceList'],
        'default_currency': frappe.db.get_value("Price List", form_data['PriceList'], 'currency'),
        'customer_type': 'Individual',
    })
        
    customer.insert()
    return customer.name

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
            'comment_by': comment['UserId'],
            'comment': comment['Text'],
        })
        
    return comments