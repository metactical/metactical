import frappe
from metactical.metactical.doctype.item_inventory_output.item_inventory_output import update_item_inventory_output, get_all_bins_for_product_bundle

@frappe.whitelist()
def receive_deletion_message(parsedContent):
    try:
        lead_source = parsedContent.get("publisher_site")
        # frappe.log_error(
        #     title="SB-Item Deletion Message Received",
        #     message=f"Received deletion message for lead source: {lead_source} \nContent: {parsedContent}"
        # )
        
        price_list = frappe.db.get_value(
            "Lead Source",
            {"name": lead_source},
            "custom_neb_price_list"
        )
        slug = parsedContent.get("Entity").get("urlSlug") if parsedContent.get("Entity") else None
        
        item_deletion_log = frappe.db.get_value("Item Drop and Create Log", {"slug": slug, "status": "Issued", "deleted": 0, "price_list": price_list}, ["product", "owner", "name"], as_dict=True)
        if not item_deletion_log:
            frappe.log_error(
                title="SB-Item Deletion Log Not Found",
                message=f"No matching Item Drop and Create Log found for slug: {slug} and price_list: {price_list}"
            )
            return False


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
                    
                    is_product_bundle = frappe.db.exists('Product Bundle', item.item_code)
                    if is_product_bundle:
                        all_bins = get_all_bins_for_product_bundle(item.item_code)
                        update_item_inventory_output(item_code=item.item_code, net_available_bins=all_bins, bundle=True, voucher_type=item.doctype)
                    else:
                        frappe.enqueue(update_item_inventory_output, item_code=item.item_code, voucher_type=item.doctype, queue='default')
                        
                all_logs = frappe.get_all(
                    "Item Drop and Create Log",
                    filters={"product": item_code, "status": "Issued", "deleted": 1},
                    order_by="creation asc",
                    fields=["name"]
                )

                for log in all_logs:
                    frappe.db.set_value("Item Drop and Create Log", log.name, "status", "Re-Created")
                    frappe.db.commit()

    except Exception as e:
        frappe.log_error(
            title="SB-Item Deletion Message Processing Error",
            message=f"Error processing deletion message: {str(e)} \nContent: {parsedContent}"
        )
        return False