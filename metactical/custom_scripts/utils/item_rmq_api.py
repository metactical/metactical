import frappe
from metactical.custom_scripts.utils.deletion_message import parsed_content

@frappe.whitelist()
def receive_deletion_message(parsedContent):
    lead_source = parsedContent.get("publisher_site")
    
    price_list = frappe.db.get_value(
        "Lead Source",
        {"name": lead_source},
        "custom_neb_price_list"
    )
    slug = parsedContent.get("Entity").get("urlSlug") if parsedContent.get("Entity") else None
    
    item_deletion_log = frappe.db.get_value("Item Drop and Create Log", {"slug": slug, "status": "Issued", "deleted": 1, "price_list": price_list}, ["product", "owner"], as_dict=True)

    item_code = item_deletion_log.product
    user = item_deletion_log.owner
    
    if not item_code or not price_list:
        frappe.log_error(
            title="SB-Item Deletion Message Error",
            message="Missing item_code or price_list in the message."
        )
        return False

    lock_key = f"item_deletion:{item_code}"

    with frappe.cache().lock(lock_key, timeout=60, blocking_timeout=60):
        frappe.db.commit()  
        
        all_logs = frappe.get_all(
            "Item Drop and Create Log",
            filters={"product": item_code, "status": "Issued", "deleted": 0, "price_list": price_list},
            order_by="creation asc",
            fields=["name", "price_list"]
        )

        for log in all_logs:
            if log.price_list == price_list:
                doc = frappe.get_doc("Item Drop and Create Log", log.name)
                doc.deleted = 1
                doc.save(ignore_permissions=True)
                frappe.db.commit()
                break

        remaining_logs = frappe.get_all(
            "Item Drop and Create Log",
            filters={"product": item_code, "status": "Issued", "deleted": 0},
            pluck="name"
        )

        if not remaining_logs:
            completion_message = f"Item Deletion for {item_code} is completed in all price lists."
            frappe.publish_realtime("msgprint", message=completion_message, user=user)
            
            variants = frappe.get_all(
                "Item",
                filters={"variant_of": item_code},
                pluck="name"
            )
            
            for variant in variants:
                item = frappe.get_doc("Item", variant)
                item.save()
