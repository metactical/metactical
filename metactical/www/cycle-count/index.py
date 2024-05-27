import frappe
from metactical.metactical.doctype.cycle_count.cycle_count import get_expected_qty

@frappe.whitelist()
def get_barcodes():
	query = """SELECT 
					ib.barcode, ib.parent AS item_code,
					item.ifw_retailskusuffix AS retail_sku, item.item_name
				FROM
					`tabItem Barcode` ib
				LEFT JOIN
					`tabItem` item ON item.name = ib.parent
				WHERE
					ib.barcode IS NOT NULL
				GROUP BY
					ib.barcode
			"""
	barcodes = frappe.db.sql(query, as_dict=1)
	return barcodes

@frappe.whitelist()
def save_cycle_count(items, warehouse, reasons):
	items = frappe.parse_json(items)
	doc = frappe.new_doc("Cycle Count")
	doc.warehouse = warehouse
	doc.reason_for_adjustment = reasons
	
	for row in items:
		expected = get_expected_qty(row.get('item_code'), warehouse)
		new_row = frappe._dict()
		new_row.item_code = row.get('item_code')
		new_row.qty = row.get('qty')
		new_row.expected_qty = expected.get("actual_qty")
		new_row.valuation_rate = expected.get("valuation_rate")
		doc.append("items", new_row)
	
	doc.save(ignore_permissions=True)
	return "Cycle Count Saved"