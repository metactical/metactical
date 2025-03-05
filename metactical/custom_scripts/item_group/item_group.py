import frappe
from frappe.integrations.doctype.webhook.webhook import enqueue_webhook


@frappe.whitelist()
def copy_specifications_to_items(item_group, overwrite, add_missing_labels, sync_to_websites):
    chunk_size = 2500
    start = 0
    webhook = frappe.get_doc("Webhook", {"webhook_doctype": "Item", "enabled": 1, "webhook_docevent": "on_update"})
    
    # Get a batch of items
    # Fetch specifications only once per batch
    web_spec_labels = frappe.get_doc('Item Group', item_group).get('neb_website_specifications')
    
    try:
        items = ['test']
        while len(items) > 0:
            items = frappe.get_all(
                'Item',
                filters={'item_group': item_group, 'disabled': 0},
                fields=['name'],
                limit_start=start,
                limit_page_length=chunk_size
            )

            if items:
                frappe.enqueue(
                    process_item_specifications,
                    items=items,
                    web_spec_labels=web_spec_labels,
                    overwrite=overwrite,
                    add_missing_labels=add_missing_labels,
                    webhook=webhook,
                    sync_to_websites=sync_to_websites,
                    queue='long'
                )
                
                start = start + chunk_size
                
    except Exception as e:
        frappe.log_error(title="Error in copy_specifications_to_items", message=frappe.get_traceback())
        frappe.msgprint(f"Error: {e}")    

def process_item_specifications(items, web_spec_labels, overwrite, add_missing_labels, webhook, sync_to_websites):
    """
    Process the specifications for a single item.
    """
    try:
        for item in items:
            item_code = item['name']
            # Check if the item already has specifications
            existing_specs = frappe.get_all(
                'MT Item Website Specification',
                filters={'parent': item_code},
                fields=['name', 'label']
            )

            if existing_specs and int(overwrite):
                for spec in existing_specs:
                    frappe.delete_doc('MT Item Website Specification', spec['name'])
            elif not int(overwrite) and existing_specs and int(add_missing_labels):
                existing_labels = [spec['label'] for spec in existing_specs]
                new_spec_found = False
                
                for label in web_spec_labels:
                    if label.label not in existing_labels:    
                        new_spec_found = True
                        insert_web_specification(item_code, label)
                        
                if not new_spec_found and int(sync_to_websites):
                    trigger_item_update(item_code, webhook)
                    
                continue
            elif not int(overwrite) and existing_specs and not int(add_missing_labels):
                continue
            
            # Insert new specifications
            for spec in web_spec_labels:
                insert_web_specification(item_code, spec)
                
            if int(sync_to_websites):
                trigger_item_update(item_code, webhook)
                
    except Exception as e: 
        frappe.log_error(title="Error in process_item_specifications", message=frappe.get_traceback())
            
def insert_web_specification(item_code, spec):
    new_spec = frappe.get_doc({
        'doctype': 'MT Item Website Specification',
        'parent': item_code,
        'parenttype': 'Item',
        'parentfield': 'neb_website_specifications',
        'label': spec.label or '',
        'mandatory': spec.mandatory or 0,
        'sort_order': spec.sort_order or 0,
        'description': spec.description or ''
    })
    new_spec.insert()
    
            
def trigger_item_update(item_code, webhook):
    if webhook:
        
        item = frappe.get_doc('Item', item_code)
        webhook = frappe.get_doc('Webhook', webhook.name)
        
        print(f"Item {item_code} updated. Triggering webhook {webhook.name}...")
        enqueue_webhook(item, webhook)