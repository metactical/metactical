# -*- coding: utf-8 -*-
# Copyright (c) 2021, Techlift Technologies and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document

class ShipstationSettings(Document):
	def validate(self):
		#Check for default shipstation settings
		default_settings = frappe.db.get_value('Shipstation Settings', {"is_default": 1})
		if default_settings:
			if self.get("is_default") == 1 and default_settings != self.name:
				frappe.throw("Error: There is another settings entry marked as default. You can only have one default setting.")
		else:
			if self.get("is_default") != 1:
				self.is_default = 1
				frappe.msgprint("Setting has been marked as default.")
				
