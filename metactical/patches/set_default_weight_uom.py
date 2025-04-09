import frappe

def execute():
    limit = 1000
    start = 0
    has_data = True

    while has_data:
        docs_list = frappe.db.get_list(
            "Item",
            fields=["name"],
            start=start,
            page_length=limit,
        )

        if len(docs_list) < limit:
            has_data = False
        
        if not docs_list:
            break
        
        frappe.enqueue(update_weight_uom, items=docs_list, queue="long")
        start = start +limit

def update_weight_uom(items):
    for doc in items:
        frappe.db.set_value("Item", doc.name, "weight_uom", "Kg", update_modified=False)
    
    frappe.db.commit()
