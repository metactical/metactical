import frappe

def execute():
    doctypes = ["Sales Invoice", "Sales Order"]
    for doctype in doctypes:
        limit = 1000
        start = 0
        has_data = True

        while has_data:
            sales_invoice_list = frappe.db.get_list(
                "Sales Invoice",
                filters={"customer_group": "Retail", "source": ""},
                fields=["name"],
                start=start,
                page_length=limit,
            )

            if not sales_invoice_list:
                has_data = False
            else:
                frappe.enqueue(update_source, sales_invoices_list=sales_invoice_list, queue="long")
                start = start +limit

def update_source(sales_invoices_list):
    for sales_invoice in sales_invoice_list:
        frappe.db.set_value("Sales Invoice", sales_invoice.name, "source", "Store - camo - downtown", update_modified=False)
    
    frappe.db.commit()
