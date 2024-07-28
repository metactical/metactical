import frappe
from tqdm import tqdm
from fuzzywuzzy import fuzz
from itertools import combinations

def delete_unlinked_customers():
	print("Getting dormant customers")
	
	# The SQL query to find unlinked customers
	query = """
	SELECT c.name, c.customer_name
	FROM `tabCustomer` c
	WHERE NOT EXISTS (
		SELECT 1 FROM `tabSales Invoice` si WHERE si.customer = c.name
	) AND NOT EXISTS (
		SELECT 1 FROM `tabSales Order` so WHERE so.customer = c.name
	) AND NOT EXISTS (
		SELECT 1 FROM `tabDelivery Note` dn WHERE dn.customer = c.name
	) AND NOT EXISTS (
		SELECT 1 FROM `tabQuotation` q WHERE q.party_name = c.name AND q.quotation_to = 'Customer'
	) AND NOT EXISTS (
		SELECT 1 FROM `tabPayment Entry` pe WHERE pe.party = c.name AND pe.party_type = 'Customer'
	) AND NOT EXISTS (
		SELECT 1 FROM `tabJournal Entry Account` jea WHERE jea.party_type = 'Customer' AND jea.party = c.name
	) AND NOT EXISTS (
		SELECT 1 FROM `tabGL Entry` gle WHERE gle.party_type = 'Customer' AND gle.party = c.name
	);
	"""
	
	# Execute the query
	unlinked_customers = frappe.db.sql(query, as_dict=True)
	
	total_customers = len(unlinked_customers)
	print(f"Found {total_customers} unlinked customers.")
	
	# Use tqdm to create a progress bar
	for customer in tqdm(unlinked_customers, desc="Deleting customers", unit="customer"):
		try:
			#Checked if linked with any adress or contact
			linked = frappe.db.sql(f"""
					SELECT name, parent, parenttype
					FROM `tabDynamic Link` 
					WHERE link_doctype='Customer' AND link_name=%(customer)s
					""", {"customer": customer.name}, as_dict=1)
			
			if len(linked) > 0:
				for link in linked:
					frappe.db.sql("""DELETE FROM `tabDynamic Link` 
						WHERE name = %(link_name)s""", {"link_name": link.name})
					
					frappe.db.sql(f"""DELETE FROM `tab{link.parenttype}` 
						WHERE name = %(parent_name)s""", {"parent_name": link.parent})
					
			# Delete customer
			frappe.db.sql("""DELETE FROM `tabCustomer` WHERE name=%(customer)s""", {"customer": customer.name})

			# Commit after each deletion to save changes
			frappe.db.commit()
		except Exception as e:
			print(f"\nError deleting customer {customer.customer_name}: {str(e)}")
	
	print("\nFinished deleting unlinked customers.")

# A function to be used in test environments to check that no customers were deleted incorrectly
def find_missing_customers():
	# Get all unique customers from Sales Orders
	sales_order_customers = frappe.db.sql("""
		SELECT DISTINCT customer
		FROM `tabSales Order`
	""", as_dict=1)
	
	# Get all customers from the Customer table
	existing_customers = frappe.db.sql("""
		SELECT name
		FROM `tabCustomer`
	""", as_dict=1)
	
	# Convert to sets for efficient comparison
	sales_order_customer_set = set(so['customer'] for so in sales_order_customers)
	existing_customer_set = set(cust['name'] for cust in existing_customers)
	
	# Find customers in Sales Orders but not in Customer table
	missing_customers = sales_order_customer_set - existing_customer_set
	
	# Print results
	if missing_customers:
		print("The following customers are in Sales Orders but not in the Customer table:")
		for customer in missing_customers:
			print(customer)
	else:
		print("All customers in Sales Orders are present in the Customer table.")
	
	return f"{len(missing_customers)} customers missing from the customer database"