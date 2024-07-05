import frappe

def on_validate(doc, method):
    if doc.is_new():
        if frappe.db.exists("Item Price", {"item_code": doc.item_code, "price_list": doc.price_list}):
            frappe.throw(f"Item Price already exists for <b>{doc.item_code}</b> in <b>{doc.price_list}</b>")