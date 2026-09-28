# Copyright (c) 2026, International Camouflage Ltd

import frappe
from frappe.model.document import Document


class ICLPricingSettings(Document):
	pass


def always_price_lists():
	"""Lists every revision must price for every item (e.g. the franchise list)."""
	return [
		r.price_list
		for r in frappe.get_single("ICL Pricing Settings").always_price_lists
		if r.price_list
	]


def max_items():
	return frappe.db.get_single_value("ICL Pricing Settings", "max_items") or 1000


def column_order():
	"""Price lists the grid shows first, in order."""
	return [r.price_list for r in frappe.get_single("ICL Pricing Settings").get("column_order") or [] if r.price_list]
