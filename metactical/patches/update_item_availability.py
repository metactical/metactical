import frappe
import csv
import os
from tqdm import tqdm
import time

def execute():
    """
    Main patch execution:
    1. Read CSV file
    2. Split into batches of 2000
    3. Queue each batch as background task
    """
    print("Starting Item Variant Availability Rule update patch")
    
    csv_file_path = os.path.join(
        frappe.get_app_path('metactical'), 
        'data', 
        'item_variant_rules.csv'
    )
    
    if not os.path.exists(csv_file_path):
        frappe.log_error(f"CSV file not found at {csv_file_path}", "Item Variant Patch")
        frappe.throw(f"CSV file not found at {csv_file_path}")
        return
    
    # Step 1: Read CSV file
    records = read_csv_file(csv_file_path)
    total_records = len(records)
        
    # Step 2: Process in batches of 2000
    batch_size = 2000
    total_batches = (total_records // batch_size) + (1 if total_records % batch_size else 0)
    
    print(f"Creating {total_batches} batches of {batch_size} records each")
    
    # Step 3: Queue each batch as background task
    for i in range(0, total_records, batch_size):
        batch = records[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        
        process_batch(batch, batch_num, total_batches)
        print("delaying for 5 seconds to avoid overload")
        time.sleep(5)
        
def read_csv_file(csv_file_path):
    """
    Step 1: Read CSV file with comma separator
    CSV Format: Skusuffix,Retailskusuffix,Onlineskusuffix,Barcode,Alias
    """
    records = []
    
    try:
        # Read CSV with comma delimiter
        with open(csv_file_path, 'r', encoding='utf-8-sig') as csvfile:
            csv_reader = csv.DictReader(csvfile, delimiter=',')
            
            line_num = 0
            for row in csv_reader:
                line_num += 1
                
                # Extract fields from your CSV format
                item_code = row.get('Retailskusuffix', '').strip()
                variant_rule = row.get('Alias', '').strip()
                
                # Only add if we have both item_code and variant_rule
                if item_code and variant_rule:
                    records.append({
                        'item_code': item_code,
                        'variant_availability_rule': variant_rule,
                        'sku_suffix': row.get('Skusuffix', '').strip(),
                        'online_sku': row.get('Onlineskusuffix', '').strip(),
                        'barcode': row.get('Barcode', '').strip()
                    })
        
        print(f"Successfully read {len(records)} valid records from CSV")
        
    except Exception as e:
        frappe.log_error(f"Error reading CSV file: {str(e)}", "CSV Read Error")
        raise
    
    return records


def process_batch(batch, batch_num, total_batches):
    print(f"Starting processing for batch {batch_num}/{total_batches}")
    
    processed = 0
    failed = 0
    skipped = 0
    
    for record in tqdm(batch):
        try:
            item_code = record.get('item_code')
            variant_rule = record.get('variant_availability_rule')
            
            if not item_code:
                skipped += 1
                continue
            
            item_code = frappe.db.exists('Item', {"ifw_retailskusuffix": item_code})
            
            # Check if item exists
            if not item_code:
                skipped += 1
                continue
            
            # Step 4: Use frappe.db.set_value() to update
            frappe.db.set_value(
                'Item',
                
                item_code,
                'neb_variantavailabilityrule',
                variant_rule,
                update_modified=False
            )
            
            processed += 1
            
            # Commit every 100 records to avoid long transactions
            if processed % 100 == 0:
                frappe.db.commit()
            
        except Exception as e:
            error_msg = f"Error updating item {record.get('item_code')}: {str(e)}"
            print(error_msg)
            frappe.log_error(error_msg, f"Batch {batch_num} - Update Error")
            failed += 1
    
    # Final commit for remaining records
    frappe.db.commit()
