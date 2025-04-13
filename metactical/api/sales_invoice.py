import frappe
from frappe import _
from metactical.metactical.page.manage_store_credit.manage_store_credit import get_returns, group_invoice_data

@frappe.whitelist()
def load_si_pos(sales_invoice):
    sales_invoice = frappe.form_dict.sales_invoice
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
    customer = { "id": invoice.customer, "Name":invoice.customer_name }
    invoice_details = {}

    for item in invoice.items:
        items.append({
            "ItemCode": item.item_code,
            "ItemName": item.item_name,
            "Rate": item.rate,
            "PriceListRate": item.price_list_rate,
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
    invoice_details["SalesPerson"] = "ifwEdmonds@camouflage.ca"
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

    returns = get_returns(invoice)
    store_credits = group_invoice_data(returns)
    frappe.response["Invoice"] = invoice_details
    frappe.response["Returns"] = store_credits
    frappe.response["Status"] = status
    frappe.response["Message"] = "Success"