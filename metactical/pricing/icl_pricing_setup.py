# Copyright (c) 2026, International Camouflage Ltd

import frappe

FRANCHISE_LIST = "RET - CamoFRN - USD"
# the grid's leading columns, in the order buyers read them
COLUMN_ORDER = ["RET - CamoFRN - USD", "RET - Camo", "RET - Gorilla", "RET - RAS", "RET - CamoUSA"]


def after_install():
	set_defaults()


def set_defaults():
	settings = frappe.get_single("ICL Pricing Settings")
	changed = False
	# every product must carry a franchise price, so revisions always price it
	if not settings.always_price_lists and frappe.db.exists("Price List", FRANCHISE_LIST):
		settings.append("always_price_lists", {"price_list": FRANCHISE_LIST, "include_all": 1})
		changed = True
	if not settings.get("column_order"):
		for pl in COLUMN_ORDER:
			if frappe.db.exists("Price List", pl):
				settings.append("column_order", {"price_list": pl})
				changed = True
	if changed:
		settings.save(ignore_permissions=True)
