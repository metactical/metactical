import frappe

def execute():
    doctypes = ["Sales Invoice", "Sales Order"]
    for doctype in doctypes:
        limit = 1000
        start = 0
        has_data = True

        while has_data:
            sales_invoice_list = frappe.db.get_list(
                doctype,
                filters={"customer_group": "Retail", "source": ""},
                fields=["name"],
                start=start,
                page_length=limit,
            )

            if not sales_invoice_list:
                has_data = False
            else:
                frappe.enqueue(update_source, sales_invoices_list=sales_invoice_list, doctype=doctype, queue="long")
                start = start +limit

def update_source(sales_invoices_list, doctype):
    for doc in sales_invoices_list:
        frappe.db.set_value(doctype, doc.name, "source", "Store - camo - downtown", update_modified=False)
    
    frappe.db.commit()
