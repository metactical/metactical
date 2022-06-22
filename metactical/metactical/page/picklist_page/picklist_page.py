import frappe
import json

@frappe.whitelist()
def get_defaults(user):
	default_settings = {}
	defaults = frappe.db.sql("""SELECT default_warehouse 
								FROM `tabPick List Settings Default` AS settings
								WHERE settings.user = %(user)s""",
							{"user": frappe.session.user}, as_dict=1)
	if len(defaults) > 0:
		default_settings = defaults[0]
	return default_settings

@frappe.whitelist()
def load_summary(warehouse):
	to_ship = 0
	to_pick = 0
	rush = 0
	same = 0
	ready_to_ship = frappe.db.sql("""SELECT 
							count(DISTINCT pli.parent) AS orders
						FROM 
							`tabPick List Item` AS pli
						LEFT JOIN
							`tabPick List` AS pl ON pl.name = pli.parent
						WHERE
							pli.warehouse = %(warehouse)s AND pl.docstatus = 0""", 
					{"warehouse": warehouse}, as_dict=1)
	items_to_pick = frappe.db.sql("""SELECT
										SUM(pli.qty) AS to_pick
									FROM
										`tabPick List Item` AS pli
									LEFT JOIN
										`tabPick List` AS pl ON pl.name = pli.parent
									WHERE
										pli.warehouse = %(warehouse)s AND pl.docstatus = 0""", 
					{"warehouse": warehouse}, as_dict=1)
	rush_orders = frappe.db.sql("""SELECT
							count(DISTINCT pli.parent) AS orders
						FROM
							`tabPick List Item` AS pli
						LEFT JOIN
							`tabPick List` AS pl ON pli.parent = pl.name
						WHERE
							pli.warehouse = %(warehouse)s AND pl.is_rush = 1 AND pl.docstatus = 0
							""", {"warehouse": warehouse}, as_dict=1)
	same_address = frappe.db.sql("""SELECT SUM(occurences) AS orders
							FROM
								(
									SELECT 
										COUNT(DISTINCT pli.parent) AS occurences
									FROM 
										`tabPick List Item` AS pli
									LEFT JOIN
										`tabPick List` AS pl ON pli.parent = pl.name
									WHERE
										pli.warehouse = %(warehouse)s AND pl.customer IS NOT NULL 
										AND pl.docstatus = 0
									GROUP BY
										pl.customer
									HAVING
										COUNT(pl.customer) > 1
 								) t
							""", {"warehouse": warehouse}, as_dict=1)
							
	if len(ready_to_ship) > 0:
		to_ship = ready_to_ship[0].orders
		
	if len(items_to_pick) > 0:
		to_pick = items_to_pick[0].to_pick
	
	if len(rush_orders) > 0:
		rush = rush_orders[0].orders
	
	if len(same_address) > 0:
		same = same_address[0].orders
	return {'ready_to_ship': to_ship, 'items_to_pick': to_pick, 'rush_orders': rush, 'same_address': same}
	
@frappe.whitelist()
def get_pick_lists(warehouse):
	pick_lists = frappe.db.sql("""SELECT
										pl.name, pl.customer, pl.is_rush, pli.sales_order
									FROM
										`tabPick List Item` AS pli
									LEFT JOIN
										`tabPick List` AS pl ON pl.name = pli.parent
									WHERE
										pl.docstatus = 0 AND pli.warehouse = %(warehouse)s
									GROUP BY pl.name, pl.customer, pl.is_rush, pli.sales_order
									ORDER BY is_rush DESC, pl.date DESC""", {"warehouse": warehouse}, as_dict=1)
	return pick_lists

@frappe.whitelist()
def get_items(pick_list, warehouse):
	items = frappe.db.sql("""SELECT
									pli.name, pli.parent, pli.item_code, pli.item_name, item.image,
									pli.ifw_location AS location, pli.qty, bin.actual_qty
								FROM
									`tabPick List Item` AS pli
								LEFT JOIN
									`tabItem` AS item ON item.item_code = pli.item_code
								LEFT JOIN
									`tabBin` AS bin ON bin.item_code = pli.item_code AND bin.warehouse = %(warehouse)s
								WHERE
									pli.parent = %(pick_list)s
								ORDER BY pli.ifw_location
								""", {"warehouse": warehouse, "pick_list": pick_list}, as_dict=1)
	for item in items:
		barcodes = frappe.db.sql("""SELECT barcode FROM `tabItem Barcode` 
						WHERE parent=%(item_code)s""", {"item_code": item.item_code}, as_dict=1)
		item.update({
			"barcodes": [row.barcode for row in barcodes]
		})
	doc = {"name": items[0].parent, "items": items}
	return doc	
	
@frappe.whitelist()
def get_order(warehouse, sales_order=None):
	if sales_order is None:
		is_rush = frappe.db.sql("""SELECT 
										soi.parent 
									FROM 
										`tabSales Order Item` AS soi
									LEFT JOIN
										`tabSales Order` AS so ON so.name = soi.parent
									WHERE
										soi.picked_qty < soi.qty AND soi.warehouse = %(warehouse)s 
										AND so.is_rush = 1 AND so.docstatus = 1
									ORDER BY so.transaction_date ASC LIMIT 1""", 
									{"warehouse": warehouse}, as_dict=1)
		if len(is_rush) > 0:
			items = frappe.db.sql("""SELECT
										soi.parent AS sales_order, (soi.qty - soi.picked_qty) AS to_pick,
										soi.image, soi.ifw_location AS location, soi.item_code, soi.item_name,
										bin.actual_qty
									FROM
										`tabSales Order Item` AS soi
									LEFT JOIN
										`tabItem` AS item ON item.name = soi.item_code 
									LEFT JOIN
										`tabBin` AS bin ON bin.item_code = soi.item_code 
										AND bin.warehouse = %(warehouse)s
									WHERE soi.parent = %(order)s
									ORDER BY item.ifw_location""", 
									{"order": is_rush[0].parent, "warehouse": warehouse}, as_dict=1)
			doc = {"name": is_rush[0].parent, "items": items}
			return doc
		else:
			order = frappe.db.sql("""SELECT 
										soi.parent 
									FROM 
										`tabSales Order Item` AS soi
									LEFT JOIN
										`tabSales Order` AS so ON so.name = soi.parent
									WHERE
										soi.picked_qty < soi.qty AND soi.warehouse = %(warehouse)s
										AND so.docstatus = 1
									ORDER BY so.transaction_date ASC LIMIT 1""", 
									{"warehouse": warehouse}, as_dict=1)
			if len(order) > 0:
				items = frappe.db.sql("""SELECT
											soi.parent AS sales_order, (soi.qty - soi.picked_qty) AS to_pick,
											soi.image, soi.ifw_location AS location, soi.item_code, soi.item_name,
											bin.actual_qty
										FROM
											`tabSales Order Item` AS soi
										LEFT JOIN
											`tabItem` AS item ON item.name = soi.item_code 
										LEFT JOIN
											`tabBin` AS bin ON bin.item_code = soi.item_code 
											AND bin.warehouse = %(warehouse)s
										WHERE soi.parent = %(order)s
										ORDER BY item.ifw_location""", 
										{"order": order[0].parent, "warehouse": warehouse}, as_dict=1)
				doc = {"name": order[0].parent, "items": items}
				return doc
			else:
				return 'None'

@frappe.whitelist()
def submit_pick_list(docname, items):
	items = json.loads(items)
	doc = frappe.get_doc('Pick List', docname)
	for item in items:
		item = frappe._dict(item)
		for row in doc.locations:
			if item.name == row.name:
				row.update({
					"picked_qty": item.picked_qty
				})
	doc.submit()
	return "Pick List Submitted"	
