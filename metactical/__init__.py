# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from frappe.utils.user import is_website_user
import frappe
from erpnext.controllers.accounts_controller import AccountsController
from metactical.custom_scripts.controllers.accounts_controller import validate_party_address

__version__ = '0.0.1'

#set_total_amount_to_default_mop = custom_default_mop
#erpnext.controllers.taxes_and_totals.calculate_taxes_and_totals.set_total_amount_to_default_mop = custom_calculate_taxes_and_totals.set_total_amount_to_default_mop

AccountsController.validate_party_address = validate_party_address

def check_app_permission():
	if frappe.session.user == "Administrator":
		return True

	if is_website_user():
		return False

	return True