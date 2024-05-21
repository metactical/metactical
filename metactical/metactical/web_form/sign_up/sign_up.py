from __future__ import unicode_literals

import frappe
from frappe import _
from urllib.parse import urlparse, parse_qs

def get_context(context):
	pass

@frappe.whitelist(allow_guest=True)
def get_provinces(country):
	provinces = frappe.get_all("Provinces", filters={"country": country}, fields=["name"])
	provinces = [province["name"] for province in provinces]
	return provinces