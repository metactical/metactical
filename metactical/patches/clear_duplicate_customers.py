import frappe
import time, sys

def execute():  
    total = 0
    BATCH_SIZE = 10000
    while True:
        customers = frappe.db.sql("""
                        SELECT name FROM (
                            SELECT c.name
                            FROM `tabCustomer` c
                            LEFT JOIN `tabGL Entry` gl ON gl.party = c.name AND gl.party_type = 'Customer'
                            LEFT JOIN `tabQuotation` q ON q.party_name = c.name AND q.quotation_to = 'Customer'
                            LEFT JOIN `tabSales Order` so ON so.customer = c.name
                            LEFT JOIN `tabSales Invoice` si ON si.customer = c.name
                            LEFT JOIN `tabPayment Entry` pe ON pe.party = c.name AND pe.party_type = 'Customer'
                            LEFT JOIN `tabDynamic Link` dl_addr ON dl_addr.link_doctype = 'Customer'
                                                                AND dl_addr.link_name = c.name
                                                                AND dl_addr.parenttype = 'Address'
                            LEFT JOIN `tabAddress` addr ON addr.name = dl_addr.parent
                            WHERE gl.name IS NULL
                            AND q.name IS NULL
                            AND so.name IS NULL
                            AND si.name IS NULL
                            AND addr.name IS NULL
                        LIMIT {limit}
                    ) AS tmp
                """.format(limit=BATCH_SIZE), as_dict=True)
        if not customers:
            break  # No more customers to delete

        customer_names = [row['name'] for row in customers]
        total += len(customer_names)

        
        batch_size = 50  # Adjust batch size as needed
        customers_to_delete = []

        for name in customer_names:
            # group the names into 25 batches
            customers_to_delete.append(name)
            if len(customers_to_delete) >= batch_size:
                delete_c(customers_to_delete)
                customers_to_delete = []
                
        if customers_to_delete:
            delete_c(customers_to_delete)
                                
        # frappe.log_error(message="Batch {} completed, {} customers deleted".format(total // BATCH_SIZE, total), title="Customer Cleanup Batch")
        print("Batch {} completed, {} customers deleted".format(total // BATCH_SIZE, total), file=sys.stdout)
        sys.stdout.flush()
        time.sleep(1)
            
    frappe.log_error(message="Total deleted customers: {}".format(total), title="Customer Cleanup Total")

def delete_c(customers_to_delete):
    # Step 1: Delete the batch
    frappe.db.sql("""
        DELETE FROM `tabCustomer`
        WHERE name IN ({})
    """.format(",".join(["%s"] * len(customers_to_delete))), tuple(customers_to_delete))
    frappe.db.commit()