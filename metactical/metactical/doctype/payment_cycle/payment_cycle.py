# -*- coding: utf-8 -*-
# Copyright (c) 2022, Techlift Technologies and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from datetime import datetime

class PaymentCycle(Document):
	def autoname(self):
		start_date = datetime.strptime(self.start_date, "%Y-%m-%d")
		end_date = datetime.strptime(self.end_date, "%Y-%m-%d")
		if self.year != str(start_date.year):
			frappe.throw("Error: The start date is not in the payment year" )
		if self.is_new():
			title = str(start_date.day) + ' ' + datetime.strftime(start_date, "%b") + ' - '\
				+ str(end_date.day) + ' ' + datetime.strftime(end_date, "%b") + ' ' + str(end_date.year)
			self.cycle_name = title
