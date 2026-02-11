# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from frappe.utils.user import is_website_user
import frappe
from erpnext.controllers.accounts_controller import AccountsController
from metactical.custom_scripts.controllers.accounts_controller import validate_party_address, validate_company_linked_addresses

__version__ = '15.0.0'

AccountsController.validate_party_address = validate_party_address
AccountsController.validate_company_linked_addresses = validate_company_linked_addresses

def check_app_permission():
	if frappe.session.user == "Administrator":
		return True

	if is_website_user():
		return False

	return True