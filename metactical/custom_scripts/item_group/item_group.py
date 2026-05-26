import frappe
from frappe.integrations.doctype.webhook.webhook import enqueue_webhook
from erpnext.setup.doctype.item_group.item_group import ItemGroup

class CustomItemGroup(ItemGroup):
    def after_rename(self, old_name, new_name, merge=False):
        super().after_rename(old_name, new_name, merge)
        
        merge_history = frappe.get_doc({
            'doctype': 'Item Group Merge History',
            'old_item_group': old_name,
            'new_item_group': new_name,
            'action': 'Rename' if not merge else 'Merge'
        })
        merge_history.insert(ignore_permissions=True)
        
    def on_trash(self):
        super().on_trash()
        
        merge_history = frappe.get_doc({
            'doctype': 'Item Group Merge History',
            'old_item_group': self.name,
            'new_item_group': "",
            'action': 'Delete'
        })
        merge_history.insert(ignore_permissions=True)
        
    def validate(self):
        super().validate()
        # Add any custom validation logic here
        
        old_doc = self.get_doc_before_save()
        old_category_names = {}
        new_category_names = {}
        
        if old_doc and old_doc.get('category_names'):
            for category in old_doc.get('category_names'):
                old_category_names[category.lead_source] = category.category_name
                
        if self.get('category_names'):
            for category in self.get('category_names'):
                new_category_names[category.lead_source] = category.category_name
                
        
        # check if any category name has changed
        category_updated = False
        if len(old_category_names) != len(new_category_names):
            self.categoy_names_updated = 1
            category_updated = True
        else:
            for lead_source, category_name in new_category_names.items():
                if lead_source in old_category_names:
                    if category_name != old_category_names[lead_source]:
                        self.categoy_names_updated = 1
                        category_updated = True
                        break
        
        if not category_updated:
            self.categoy_names_updated = 0    

@frappe.whitelist()
def copy_specifications_to_items(item_group, add_missing_labels):
    chunk_size = 2500
    start = 0
        
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
                    queue='long'
                )
                
                start = start + chunk_size
  
    except Exception as e:
        frappe.log_error(title="Error in copy_specifications_to_items", message=frappe.get_traceback())
        frappe.msgprint(f"Error: {e}")    

def process_item_specifications(items, web_spec_labels):
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

            if existing_specs:
                existing_labels = [spec['label'] for spec in existing_specs]
                new_spec_found = False
                
                for label in web_spec_labels:
                    if label.label not in existing_labels:    
                        new_spec_found = True
                        insert_web_specification(item_code, label)
                
                update_website_items(item_code)
                frappe.db.commit()
                continue
            
            # Insert new specifications
            for spec in web_spec_labels:
                insert_web_specification(item_code, spec)
            
            update_website_items(item_code)
            frappe.db.commit()
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
        'description': spec.description or ''
    })
    new_spec.insert()
    
            
def trigger_item_update(item_code, webhook):
    if webhook:
        
        item = frappe.get_doc('Item', item_code)        
        enqueue_webhook(item, webhook)
        
def update_website_items(item_code):
    website_items = frappe.get_all("Website Item", filters={"item_code": item_code}, fields=["name"])
    if website_items:
        for item in website_items:
            website_item = frappe.get_doc("Website Item", item.name)
            website_item.neb_website_specifications = []
            website_item.website_specifications = []
            website_item.save()
            
            item = frappe.get_doc('Item', item_code)
            for spec in item.neb_website_specifications:
                website_spec = frappe.new_doc("MT Item Website Specification")
                website_spec.label = spec.label
                website_spec.description = spec.description
                website_spec.mandatory = spec.mandatory
                website_spec.parent = website_item.name
                website_spec.parenttype = website_item.doctype
                website_spec.parentfield = "neb_website_specifications"
                website_spec.save(ignore_permissions=True)

                main_website_spec = frappe.new_doc("Item Website Specification")
                main_website_spec.label = spec.label
                main_website_spec.description = spec.description
                main_website_spec.parent = website_item.name
                main_website_spec.parenttype = website_item.doctype
                main_website_spec.parentfield = "website_specifications"
                main_website_spec.save(ignore_permissions=True)