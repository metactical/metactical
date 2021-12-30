# -*- coding: utf-8 -*-
# Copyright (c) 2021, Techlift Technologies and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document

class CycleCount(Document):
	def on_submit(self):
		doc = frappe.new_doc("Stock Reconciliation");
		doc.update({
			"purpose": "Stock Reconciliation",
			"ais_cycle_count": self.name
		})
		for row in self.items:
			doc.append("items", {
				"item_code": row.item_code,
				"warehouse": self.warehouse,
				"qty": row.qty,
				"valuation_rate": row.valuation_rate
			})
		doc.submit()

@frappe.whitelist()
def get_expected_qty(item_code, warehouse):
	expected = frappe.db.sql('''SELECT actual_qty, valuation_rate FROM `tabBin` 
								WHERE item_code = %(item_code)s AND warehouse = %(warehouse)s''', 
								{"item_code": item_code, "warehouse": warehouse}, as_dict=1)
	if expected and len(expected) > 0:
		ret = {"actual_qty": expected[0].actual_qty, "valuation_rate": expected[0].valuation_rate}
		return ret
	else:
		return {"actual_qty": 0, "valuation_rate": 0}
