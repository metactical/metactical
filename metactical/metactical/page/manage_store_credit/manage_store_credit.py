import frappe

@frappe.whitelist()
def search_customer(*args, **kwargs):
    phone_number = kwargs.get('phone_number')
    email = kwargs.get('email')
    print("start")

    filters = {}
    if phone_number:
        filters.update({"phone": ["like", "%{}%".format(phone_number)]})
    if email:
        filters.update({"email_id": ["like", "%{}%".format(email)]})
    print(filters)

    contact = frappe.db.get_list("Contact",
                or_filters=filters,
                fields=["name", "email_id"]
            )

    email_ids = [c.get('email_id') for c in contact]
    customers = frappe.db.get_list("Customer",
                            filters={
                                "ifw_email": ["in", email_ids]
                            },
                            fields=["name", "first_name", "last_name", "ais_company", "ifw_email"]
                        )
                        
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
                "discount": item.discount_amount
            })

        taxes_list = []
        for tax in sales_invoice_doc.taxes:
            taxes_list.append({
                "name": tax.charge_type,
                "amount": frappe.format_value(tax.tax_amount, {"fieldtype": "Currency"})
            })
        
        taxes["taxes"] = taxes_list
        taxes["TTL Tax"] = frappe.format_value(sales_invoice_doc.total_taxes_and_charges, {"fieldtype": "Currency"}) if sales_invoice_doc else "0"
        taxes["Discount"] = frappe.format_value(sales_invoice_doc.discount_amount, {"fieldtype": "Currency"}) if sales_invoice_doc else ""
        taxes["TTL Store Credit"] = frappe.format_value(sales_invoice_doc.grand_total, {"fieldtype": "Currency"}) if sales_invoice_doc else ""
        taxes["Total Qty Returned"] = sales_invoice_doc.total_qty if sales_invoice_doc else ""
        
    frappe.response["items"] = items
    frappe.response["taxes"] = taxes
    frappe.response["customer"] = sales_invoice_doc.customer if sales_invoice_doc else ""