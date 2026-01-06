import frappe
from frappe import _
from metactical.custom_scripts.utils.metactical_utils import get_returns, group_invoice_data

@frappe.whitelist()
def load_si_from_so_pos(sales_order):
    sales_order = frappe.db.exists("Sales Order", sales_order)

    if not sales_order:
        frappe.response["Status"] = 404
        frappe.response["Message"] = "Sales Order not found"
        return
    
    sales_order = frappe.get_doc("Sales Order", sales_order)
    if sales_order.docstatus > 1:
        frappe.response["Status"] = 404
        frappe.response["Message"] = "Sales Order is cancelled"
        return
    if sales_order.docstatus == 0:
        frappe.response["Status"] = 404
        frappe.response["Message"] = "Sales Order is Draft"
        return
    
    sales_invoice = get_sales_invoice(sales_order.name)
    if sales_invoice:
        sales_invoice = load_si_pos(sales_invoice.parent)
    else:
        frappe.response["Status"] = 404
        frappe.response["Message"] = f"{sales_order.name} has no Paid or Credit Note Issued Sales Invoice"

def get_sales_invoice(sales_order):
    sales_invoices = frappe.db.sql("""
        SELECT `tabSales Invoice Item`.parent, si.status, si.docstatus FROM `tabSales Invoice Item`
        JOIN `tabSales Invoice` si ON si.name = `tabSales Invoice Item`.parent
        Where
        `tabSales Invoice Item`.sales_order = %s 
        and is_return = 0 
        and si.docstatus = 1
        and si.status in ("Paid", "Credit Note Issued")
        and (si.source like "Store%%" or is_pos = 1)
        order by si.posting_date asc
        """, (sales_order,), as_dict=True)
        
    invoice = sales_invoices[0] if sales_invoices else None
    return invoice

@frappe.whitelist()
def load_si_pos(sales_invoice):
    message = ""
    status = 200
    invoice = None
    if frappe.db.exists("Sales Invoice", sales_invoice):
        invoice = frappe.get_doc("Sales Invoice", sales_invoice)
        if (invoice.docstatus > 1):
            message = "Sales Invoice is "+invoice.get("status")
            status = 500
        elif invoice.docstatus == 0:
            message = "Sales Invoice "+sales_invoice+" is a Draft"
            status = 500
        elif invoice.status not in ["Paid", "Credit Note Issued"]:
            message = "Sales Invoice "+sales_invoice+" is "+invoice.get("status")
            status = 500
    
    if not invoice:
        message = "Sales Invoice not found"
        status = 404    
    
    if message:
        frappe.response["Status"] = status
        frappe.response["Message"] = message
        return
    
    items = []
    taxes = []
    payments = []
    
    customer = get_address_detail(invoice)
    customer["id"] = invoice.customer
    customer_name = frappe.db.get_value("Customer", invoice.customer, ["first_name", "last_name"], as_dict=True)
    customer["FirstName"] = customer_name.get("first_name") if customer_name else ""
    customer["LastName"] = customer_name.get("last_name") if customer_name else ""
        
    invoice_details = {}

    for item in invoice.items:
        retail_sku = item.ifw_retailskusuffix if item.ifw_retailskusuffix else frappe.get_value("Item", item.item_code, "ifw_retailskusuffix")
        items.append({
            "ItemCode": item.item_code,
            "ItemName": item.item_name,
            "RetailSku": retail_sku,
            "Rate": item.rate,
            "PriceListRate": item.price_list_rate,
            "Image": item.image,
            "Qty": item.qty,
            "Amount": frappe.format_value(item.net_amount, {"fieldtype": "Currency"}),
            "Discount": item.discount_percentage,
        })
    for tax in invoice.taxes:
        tax_name = tax.account_head.split(" - ")[0]
        taxes.append({
            "TaxId": tax_name,
            "Amount": tax.rate
        })

    for payment in invoice.payments:
        payments.append({
            "ModeOfPayment": payment.mode_of_payment,
            "Amount": payment.amount,
            "Change": invoice.change_amount if payment.mode_of_payment == "Cash" else 0,
        })

    pos_profile = ""
    if invoice.pos_profile:
        pos_profile = invoice.pos_profile.replace(" Operators", "")

    invoice_details["ApprovalList"] = []
    invoice_details["SalesPerson"] = invoice.owner
    invoice_details["Comments"] = []
    invoice_details["InvoiceId"] = invoice.name
    invoice_details["Total"] = invoice.grand_total
    invoice_details["PriceList"] = invoice.selling_price_list
    invoice_details["PostingDate"] = invoice.posting_date
    invoice_details["OverallDiscount"] = invoice.additional_discount_percentage
    invoice_details["TaxesAndChargesTemplate"] = invoice.taxes_and_charges
    invoice_details["POSProfile"] = pos_profile
    invoice_details["LeadSource"] = invoice.source
    invoice_details["total_taxes_and_charges"] = invoice.total_taxes_and_charges
    invoice_details["Items"] = items
    invoice_details["Taxes"] = taxes
    invoice_details["Customer"] = customer
    invoice_details["Payment"] = payments
    invoice_details["Status"] = invoice.status

    returns = get_returns(invoice)
    store_credits = group_invoice_data(returns)
    frappe.response["Invoice"] = invoice_details
    frappe.response["Returns"] = store_credits
    frappe.response["Status"] = status
    frappe.response["Message"] = "Success"

@frappe.whitelist()
def load_so_pos(sales_order):
    sales_order = frappe.db.exists("Sales Order", sales_order)

    if not sales_order:
        frappe.response["Status"] = 404
        frappe.response["Message"] = "Sales Order not found"
        return
    
    sales_order = frappe.get_doc("Sales Order", sales_order)
    if sales_order.docstatus > 1:
        frappe.response["Status"] = 404
        frappe.response["Message"] = "Sales Order is cancelled"
        return
    
    order_details = {}
    
    order_details["ApprovalList"] = []
    order_details["SalesPerson"] = sales_order.owner
    order_details["Comments"] = []
    order_details["InvoiceId"] = sales_order.name
    order_details["Total"] = sales_order.grand_total
    order_details["PriceList"] = sales_order.selling_price_list
    order_details["PostingDate"] = sales_order.transaction_date
    order_details["OverallDiscount"] = sales_order.additional_discount_percentage
    order_details["TaxesAndChargesTemplate"] = sales_order.taxes_and_charges
    order_details["POSProfile"] = None
    order_details["LeadSource"] = sales_order.source
    order_details["total_taxes_and_charges"] = sales_order.total_taxes_and_charges
    order_details["Items"] = []
    order_details["Taxes"] = []
    order_details["Payment"] = []
    order_details["Customer"] = {"id": sales_order.customer, "FirstName": sales_order.customer_name}
    order_details["Status"] = sales_order.status
    order_details["HasInvoice"] = so_has_invoice(sales_order.name)
    
    # Get Items and Taxes 
    for item in sales_order.items:
        reatil_sku = item.ifw_retailskusuffix if item.ifw_retailskusuffix else frappe.get_value("Item", item.item_code, "ifw_retailskusuffix")
        order_details["Items"].append({
            "ItemCode": item.item_code,
            "ItemName": item.item_name,
            "RetailSku": reatil_sku,
            "Rate": item.rate,
            "PriceListRate": item.price_list_rate,
            "Image": item.image,
            "Qty": item.qty,
            "Amount": frappe.format_value(item.net_amount, {"fieldtype": "Currency"}),
            "Discount": item.discount_percentage,
        })
        
    for tax in sales_order.taxes:
        tax_name = tax.account_head.split(" - ")[0]
        order_details["Taxes"].append({
            "TaxId": tax_name,
            "Amount": tax.rate
        })
        
    # Get Payments
    payment_entries = frappe.db.sql("""
                                    SELECT pe.mode_of_payment,
                                        pe.paid_amount
                                        FROM 
                                        `tabPayment Entry` pe
                                        INNER JOIN 
                                        `tabPayment Entry Reference` per 
                                        ON per.parent = pe.name
                                        WHERE 
                                        per.reference_doctype = 'Sales Order'
                                        AND per.reference_name = %s
                                        AND pe.docstatus = 1
                                    """, (sales_order.name), as_dict=True)
    
    for payment in payment_entries:
        order_details["Payment"].append({
            "ModeOfPayment": payment.mode_of_payment,
            "Amount": payment.paid_amount
        })
        
    address = get_address_detail(sales_order)
    customer = frappe.db.get_value("Customer", sales_order.customer, ["first_name", "last_name"], as_dict=True)
    
    if customer:
        order_details["Customer"]["FirstName"] = customer.get("first_name")
        order_details["Customer"]["LastName"] = customer.get("last_name")
    
    if address:
        order_details["Customer"].update(address)
    
    frappe.response["Invoice"] = order_details
    frappe.response["Status"] = 200
    frappe.response["Message"] = "Success"
    
def so_has_invoice(sales_order):
    sales_invoices = frappe.db.sql("""
        SELECT `tabSales Invoice Item`.parent, si.status, si.docstatus FROM `tabSales Invoice Item`
        JOIN `tabSales Invoice` si ON si.name = `tabSales Invoice Item`.parent
        Where
        `tabSales Invoice Item`.sales_order = %s 
        and is_return = 0 
        and si.docstatus <> 2
        order by si.posting_date asc
        """, (sales_order), as_dict=True)
        
    return True if sales_invoices else False
    
def get_address_detail(sales_order):
    
    customer = frappe.db.exists("Customer", sales_order.customer)
    if not customer:
        return {}
    
    customer = {}
    if sales_order.shipping_address_name:
        address = frappe.get_doc("Address", sales_order.shipping_address_name, ["email_id", "phone", "mobile_no"], as_dict=True)
    else:
        return {}
    
    if not address:
        return {}
    
    customer_contact = address
    customer["Email"] = customer_contact.get("email_id")
    customer["Phone"] = customer_contact.get("phone") or customer_contact.get("mobile_no")
    customer["AddressLine1"] = customer_contact.get("address_line1")
    customer["AddressLine2"] = customer_contact.get("address_line2")
    customer["City"] = customer_contact.get("city")
    customer["State"] = customer_contact.get("state")
    customer["ZipCode"] = customer_contact.get("pincode")
    customer["Country"] = customer_contact.get("country")
    
    return customer