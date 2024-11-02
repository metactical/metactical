import frappe

@frappe.whitelist(allow_guest=True)
def get_items():
	query = """SELECT 
					ib.barcode, ib.parent AS item_code,
					item.ifw_retailskusuffix AS retail_sku, item.item_name
				FROM
					`tabItem Barcode` ib
				LEFT JOIN
					`tabItem` item ON item.name = ib.parent
				WHERE
					ib.barcode IS NOT NULL AND item.disabled = 0
					AND item.is_stock_item = 1 AND item.has_serial_no = 0
				GROUP BY
					ib.barcode
			"""
	barcodes = frappe.db.sql(query, as_dict=1)
	return barcodes

@frappe.whitelist(allow_guest=True)
def get_warehouses(item_code):
	query = """SELECT 
					actual_qty AS qty, warehouse AS name,
					valuation_rate, '' AS error
				FROM
					`tabBin`
				WHERE
					item_code = %s AND actual_qty > 0
				GROUP BY
					warehouse
			"""
	warehouses = frappe.db.sql(query, item_code, as_dict=1)
	
	# Add serial nos according to qty
	serial_nos = []
	for warehouse in warehouses:
		qty = warehouse.get('qty')
		while qty > 0:
			serial_nos.append('')
			qty -= 1
		warehouse['serials'] = serial_nos
	return warehouses

@frappe.whitelist(allow_guest=True)
def save_serial_numbers(item_code, warehouses):
	warehouses = frappe.parse_json(warehouses)
	doc = frappe.new_doc("Stock Reconciliation")
	doc.purpose = "Stock Reconciliation"
	doc.ais_reason_for_adjustment = "Zeroing out stock for serial number reconciliation"
	for row in warehouses:
		doc.append("items", {
			"item_code": item_code,
			"warehouse": row.get('name'),
			"valuation_rate": row.get('valuation_rate'),
			"qty": 0
		})
	doc.submit()

	frappe.db.set_value("Item", item_code, "has_serial_no", 1)

	doc = frappe.new_doc("Stock Reconciliation")
	doc.purpose = "Stock Reconciliation"
	doc.ais_reason_for_adjustment = "Reconciling serial numbers"
	for row in warehouses:
		serial_nos = ""
		for serial_no in row.get("serials"):
			serial_nos += serial_no + "\n"
		doc.append("items", {
			"item_code": item_code,
			"warehouse": row.get('name'),
			"valuation_rate": row.get('valuation_rate'),
			"qty": row.get('qty'),
			"serial_no": serial_nos
		})
	doc.submit()
	return "success"