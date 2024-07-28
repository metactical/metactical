import frappe
import click
from frappe.commands import pass_context, get_site
from frappe.exceptions import SiteNotSpecifiedError
from metactical.utils.dormant_customers import delete_unlinked_customers

@click.command("delete-dormant-customers")
@pass_context
def delete_dormant_customers(context):
	site = get_site(context)
	if not site:
		raise SiteNotSpecifiedError
	
	frappe.init(site=site)
	frappe.connect()
	delete_unlinked_customers()

commands = [
	delete_dormant_customers
]
