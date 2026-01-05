# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from frappe.utils.user import is_website_user
import frappe

__version__ = '15.0.0'

def check_app_permission():
	if frappe.session.user == "Administrator":
		return True

	if is_website_user():
		return False

	return True