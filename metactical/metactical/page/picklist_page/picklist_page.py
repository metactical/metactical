import frappe
import json

@frappe.whitelist()
def get_defaults(user):
	default_settings = {}
	defaults = frappe.db.sql("""SELECT 
									default_warehouse, default_location 
								FROM 
									`tabPick List Settings Default` AS settings
								WHERE 
									settings.user = %(user)s""",
							{"user": frappe.session.user}, as_dict=1)
	if len(defaults) > 0:
		default_settings = defaults[0]
	return default_settings

@frappe.whitelist()
def load_summary(warehouse, source):
	to_ship = 0
	to_pick = 0
	rush = 0
	same = 0
	where = ''
	where_filter = {"warehouse": warehouse}
	if source != "All":
		where = " AND pl.ais_source = %(source)s "
		where_filter.update({"source": source})
	picklists = frappe.db.sql("""
			SELECT
				pl.name, pl.customer, pl.is_rush, pli.qty
			FROM
				`tabPick List Item` AS pli
			LEFT JOIN
				`tabPick List` AS pl ON pl.name = pli.parent
			LEFT JOIN
				`tabSales Order` AS sales_order ON pli.sales_order = sales_order.name
			WHERE
				pli.warehouse = %(warehouse)s AND pl.docstatus = 0
				AND sales_order.status <> 'On Hold'""" + where,
			where_filter, as_dict=1)
	
	customers = []
	orders = []
	for picklist in picklists:
		to_pick += picklist.qty
		if picklist.is_rush == 1 and picklist.name not in orders:
			rush += 1

		if picklist.customer is not None and picklist.customer != '':
			if picklist.customer in customers and picklist.name not in orders:
				same += 1
			else:
				customers.append(picklist.customer)

		if picklist.name not in orders:
			orders.append(picklist.name)
	to_ship = len(orders)
	return {'ready_to_ship': to_ship, 'items_to_pick': to_pick, 'rush_orders': rush, 'same_address': same}
	
@frappe.whitelist()
def get_pick_lists(warehouse, filters, source, qty_order):
	where = ''
	if filters != "":
		where = " AND pl.name LIKE '%{where_f}%'".format(where_f = filters)
	if source != "All":
		where = " AND pl.ais_source = '{source}'".format(source = source)
	pick_lists = frappe.db.sql(f"""SELECT
										pl.name, pl.customer, pl.is_rush, pli.sales_order,
										COUNT(pli.name) AS qty_item
									FROM
										`tabPick List Item` AS pli
									LEFT JOIN
										`tabPick List` AS pl ON pl.name = pli.parent
									LEFT JOIN
										`tabItem` AS item ON item.name = pli.item_code
									LEFT JOIN
										`tabSales Order` AS sales_order ON sales_order.name = pli.sales_order
									WHERE
										pl.docstatus = 0 AND pli.warehouse = '{warehouse}'
										AND item.is_stock_item = 1 AND sales_order.status <> 'On Hold'
										AND (pl.ais_picked_by IS NULL OR pl.ais_picked_by = '')
										{where}
									GROUP BY pl.name, pl.customer, pl.is_rush, pli.sales_order
									ORDER BY 
										is_rush DESC, 
										qty_item {qty_order}, 
										pl.date DESC""", 
								as_dict=1)
	return pick_lists

@frappe.whitelist()
def get_items(pick_list, warehouse, user, tote):
	is_being_picked = frappe.db.get_value('Pick List', pick_list, 'ais_picked_by')
	shipped_items = frappe.db.sql("""SELECT item FROM `tabPick List Shipping Item`""", as_dict=1)
	not_include = "("
	i = 0
	for row in shipped_items:
		i = i+1
		not_include += f"'{row.item}'"
		if len(shipped_items) != i:
			not_include += ","
	not_include += ")"
	if is_being_picked is None or is_being_picked == '':
		items = frappe.db.sql("""SELECT
										pli.name, pli.parent AS pick_list, pli.item_code, pli.item_name, item.image,
										pli.ifw_location AS locations, pli.qty, bin.actual_qty
									FROM
										`tabPick List Item` AS pli
									LEFT JOIN
										`tabItem` AS item ON item.item_code = pli.item_code
									LEFT JOIN
										`tabBin` AS bin ON bin.item_code = pli.item_code AND bin.warehouse = %(warehouse)s
									WHERE
										pli.parent = %(pick_list)s AND pli.item_code not in """ + not_include + """
									ORDER BY pli.ifw_location
									""", {"warehouse": warehouse, "pick_list": pick_list}, as_dict=1)
		for item in items:
			barcodes = frappe.db.sql("""SELECT barcode FROM `tabItem Barcode` 
							WHERE parent=%(item_code)s""", {"item_code": item.item_code}, as_dict=1)
			locations = []
			if item.get('locations') not in [None, ""]:
				locations = item.get('locations').split("|")
			item.update({
				"barcodes": [row.barcode for row in barcodes],
				"locations": [location.strip() for location in locations],
				"tote": tote
			})
		frappe.db.set_value('Pick List', pick_list, 'ais_picked_by', user)
		doc = {"name": items[0].pick_list, "items": items}
		return doc
	else:
		return 'Already Picked'
	
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
def submit_pick_list(items):
	items = json.loads(items)
	pick_lists = []
	totes = []
	delivery_notes = {}
	for item in items:
		item = frappe._dict(item)
		if item.pick_list not in pick_lists:
			pick_lists.append(item.pick_list)
		if item.get('tote') is not None and item.get('tote') not in totes:
			totes.append(item.tote)
	for pick_list in pick_lists:
		doc = frappe.get_doc('Pick List', pick_list)
		for item in items:
			item = frappe._dict(item)
			if item.pick_list == pick_list:
				for row in doc.locations:
					# Because all items are initialized with picked qty =1 
					# No need to take into consideration shipping items
					if item.name == row.name:
						if item.picked_qty == 0:
							doc.remove(row)
						else:
							row.update({
								"picked_qty": item.picked_qty
							})
		doc.submit()
		#Get associated delivery note
		delivery_note = frappe.db.get_value('Delivery Note', {'pick_list': pick_list}, 'name')
		delivery_notes.update({pick_list: delivery_note})
	#Add to totes
	for tote in totes:
		doc = frappe.get_doc('Picklist Tote', tote)
		for item in items:
			item = frappe._dict(item)
			if item.tote == tote:
				doc.append('tote_items', {
					"item": item.item_code,
					"pick_list": item.pick_list,
					"pick_list_item": item.name,
					"qty": item.picked_qty
				})
		doc.update({"current_delivery_note": delivery_notes[doc.tote_items[0].pick_list]})
		doc.save()			
	return "Pick List Submitted"
	
@frappe.whitelist()
def close_pick_list(pick_list):
	frappe.db.set_value('Pick List', pick_list, 'ais_picked_by', '')
	
@frappe.whitelist()
def clear_totes_picklist(totes, pick_lists):
	totes = json.loads(totes)
	pick_lists = json.loads(pick_lists)
	
	#Clear totes
	where_t = ""
	for tote in totes:
		where_t += ",'{}'".format(tote)
	where_t = where_t[1:]
	frappe.db.sql("""UPDATE `tabPicklist Tote` SET used_by = '' WHERE name IN ({})""".format(where_t))
	
	#Clear pick lists
	where_p = ""
	for pick_list in pick_lists:
		where_p += ",'{}'".format(pick_list)
	where_p = where_p[1:]
	frappe.db.sql("""UPDATE `tabPick List` SET ais_picked_by='' WHERE name IN ({})""".format(where_p))		
	
@frappe.whitelist()
def get_totes(warehouse):
	query = frappe.db.sql("""SELECT
								tote_number
							FROM 
								`tabPicklist Tote`
							WHERE
								warehouse = %(warehouse)s AND (used_by IS NULL OR used_by = '')
								AND name NOT IN (SELECT DISTINCT parent FROM `tabPicklist Tote Item`)""", 
			{"warehouse": warehouse}, as_dict=1)
	totes = []
	for tote in query:
		if tote.tote_number is not None:
			totes.append(tote.tote_number)
	return totes
	
@frappe.whitelist()
def get_tote_items(warehouse, pick_lists, user, totes):
	totes = json.loads(totes)
	pick_lists = json.loads(pick_lists)
	pls_list = []
	where_pick = "("
	i = 0
	for pl in pick_lists:
		pls_list.append(pl)
		if i > 0:
			where_pick += ','
		where_pick += "'" + pl + "'"
		i = i+1
	where_pick += ")"

	shipped_items = frappe.db.sql("""SELECT item FROM `tabPick List Shipping Item`""", as_dict=1)
	not_include = "("
	i = 0
	for row in shipped_items:
		i = i+1
		not_include += f"'{row.item}'"
		if len(shipped_items) != i:
			not_include += ","
	not_include += ")"

	items = frappe.db.sql(f"""SELECT 
								pli.name, pli.item_code, pli.item_name, item.image,
								pli.ifw_location AS locations, pli.qty, bin.actual_qty,
								pli.parent AS pick_list
							FROM
								`tabPick List Item` AS pli
							LEFT JOIN
								`tabItem` AS item ON item.name = pli.item_code
							LEFT JOIN
								`tabBin` AS bin ON bin.item_code = pli.item_code AND bin.warehouse = %(warehouse)s
							WHERE
								pli.parent in {where_pick} AND pli.item_code NOT IN {not_include}
							ORDER BY
								pli.ifw_location""",
						{"warehouse": warehouse}, as_dict=1)
	#SEt the pick list to being picked
	query = frappe.db.sql("""UPDATE `tabPick List` SET ais_picked_by = %(user)s WHERE name in """ + where_pick, {"user": user})
	for item in items:
		barcodes = frappe.db.sql("""SELECT barcode FROM `tabItem Barcode` 
						WHERE parent=%(item_code)s""", {"item_code": item.item_code}, as_dict=1)
		locations = []
		if item.get('locations') not in [None, ""]:
			locations = item.get('locations').split("|")
		item.update({
			"barcodes": [row.barcode for row in barcodes],
			"locations": [location.strip() for location in locations]
		})
		
	#Set the totes to being used
	where_t = ''
	for tote in totes:
		where_t += ",'" + tote + "'"
	where_t = where_t[1:]
	query = """UPDATE `tabPicklist Tote` SET used_by=%(user)s WHERE name IN (""" + where_t + """)"""
	frappe.db.sql(query, {"user": user})
	return {"pick_lists": pls_list, "items": items}
