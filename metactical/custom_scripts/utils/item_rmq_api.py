import frappe

def receive_deletion_message(processed_content):
    try:
        item_code = processed_content.get("item_code")
        price_list = processed_content.get("price_list")
        user = processed_content.get("user")
        status = processed_content.get("status")
        message = processed_content.get("message", f"Item Deletion for {item_code} in {price_list} is failed or incomplete with status: {status}.")
        
        if not item_code or not price_list:
            frappe.log_error(title="SB-Item Deletion Message Error", message="Missing item_code or price_list in the message.")
            
        if processed_content.get("status") != "Completed":
            frappe.publish_realtime("msgprint", message=message, user=user)
            return
        
        all_logs = frappe.get_all("Item Drop and Create Log", filters={"product": item_code, "status": "Issued"}, order_by="creation asc", fields="*")
        print(all_logs)
        
        for log in all_logs:
            if log.price_list == price_list:
                log.status = "Completed"
                log.save(ignore_permissions=True)
                frappe.db.commit()
                break
            
    except Exception as e:
        frappe.log_error(title="SB-Item Deletion Message Error", message=str(e))