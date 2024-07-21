import frappe
from frappe.model.naming import getseries
from tqdm import tqdm
import click
from frappe.commands import pass_context, get_site
from frappe.exceptions import SiteNotSpecifiedError

@click.command("rename-customers")
@pass_context
def rename_customers(context):
	site = get_site(context)
	if not site:
		raise SiteNotSpecifiedError

	frappe.init(site=site)
	frappe.connect()

	customers = frappe.db.sql("""SELECT name FROM `tabCustomer` 
						   WHERE name NOT LIKE 'CS%'
						   ORDER BY modified DESC
						   """, as_dict=1)

	for customer in tqdm(customers, desc="Renaming customers", unit="customer"):
		old_name = customer.name
		new_name = f"CS{getseries('CS', 5)}"
		try:
			frappe.rename_doc("Customer", old_name, new_name)
			frappe.db.commit()
		except Exception as e:
			frappe.log_error(f"Failed to rename {old_name}: {e}")

commands = [
	rename_customers
]
