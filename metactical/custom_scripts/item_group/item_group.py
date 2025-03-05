import frappe

@frappe.whitelist()
def copy_specification_from_item_group(item_group, overwrite, add_missing_labels):
    chunk_size = 3
    start = 0
    # Get a batch of items
    # Fetch specifications only once per batch
    web_spec_labels = frappe.get_doc('Item Group', item_group).get('neb_website_specifications')
    
    items = ['test']
    while len(items) > 0:
        items = frappe.get_all(
            'Item',
            filters={'item_group': item_group},
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
                queue='default'
            )
            
            start = start + chunk_size


def process_item_specifications(items, web_spec_labels, overwrite, add_missing_labels):
    """
    Process the specifications for a single item.
    """
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
            for label in web_spec_labels:
                if label.label not in existing_labels:    
                    new_spec = frappe.get_doc({
                        'doctype': 'MT Item Website Specification',
                        'parent': item_code,
                        'parenttype': 'Item',
                        'parentfield': 'neb_website_specifications',
                        'label': label.label,
                        'mandatory': label.mandatory,
                    })
                    new_spec.insert()
            continue
        elif not int(overwrite) and existing_specs and not int(add_missing_labels):
            continue
        
        # Insert new specifications
        for spec in web_spec_labels:
            new_spec = frappe.get_doc({
                'doctype': 'MT Item Website Specification',
                'parent': item_code,
                'parenttype': 'Item',
                'parentfield': 'neb_website_specifications',
                'label': spec.label,
                'mandatory': spec.mandatory,
            })
            new_spec.insert()
