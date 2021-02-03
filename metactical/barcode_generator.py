# -*- coding: utf-8 -*-
# Copyright (c) 2020, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
import shutil
import barcode
from pathlib import Path
import pyqrcode


def generate(self, method):
	code = self.name
	name_tobe = code+".svg"
	check_file = Path("site1.local/public/files/"+name_tobe)
	if not check_file.is_file():
		bar = barcode.get('code128', str(code))
		result = bar.save(code)
		shutil.move(result, 'site1.local/public/files')

def po_validate(self, method):
	self.customer_address=None
	for d in self.items:
		if d.sales_order:
			self.customer_address = frappe.db.get_value("Sales Order", d.sales_order, "address_display")
			break