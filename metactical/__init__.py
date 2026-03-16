# -*- coding: utf-8 -*-
from __future__ import unicode_literals

__version__ = '15.0.0'

try:
	from erpnext.controllers.accounts_controller import AccountsController
	from metactical.custom_scripts.controllers.accounts_controller import validate_party_address, validate_company_linked_addresses
	AccountsController.validate_party_address = validate_party_address
	AccountsController.validate_company_linked_addresses = validate_company_linked_addresses
except ImportError:
	pass

def check_app_permission():
	import frappe
	from frappe.utils.user import is_website_user

	if frappe.session.user == "Administrator":
		return True

	if is_website_user():
		return False

	return True