import frappe
import json
import copy

@frappe.whitelist()
def get_defaults():
	default_settings = {}
	defaults = frappe.db.sql("""SELECT 
									default_warehouse, default_location, last_filters
								FROM 
									`tabPick List Settings Default` AS settings
								WHERE 
									settings.user = %(user)s""",
							{"user": frappe.session.user}, as_dict=1)
	if len(defaults) > 0:
		default_settings = defaults[0]

		if default_settings.get("last_filters"):
			try:
				filters_dict = json.loads(default_settings.get("last_filters"))

				if filters_dict.get("last_warehouse"):
					default_settings["default_warehouse"] = filters_dict.get("last_warehouse")

				if filters_dict.get("last_country"):
					default_settings["last_country"] = filters_dict.get("last_country", "")

				if filters_dict.get("last_source"):
					default_settings["last_source"] = filters_dict.get("last_source")

				if filters_dict.get("sort_by"):
					default_settings["sort_by"] = filters_dict.get("sort_by")

				if filters_dict.get("sort_order"):
					default_settings["sort_order"] = filters_dict.get("sort_order")
			
			except (json.JSONDecodeError, TypeError):
				# Handle invalid JSON or if last_filters is None
				default_settings["last_country"] = frappe.db.get_single_value("Pick List Settings", "default_country") or "All"
		else:
			default_settings["last_country"] = frappe.db.get_single_value("Pick List Settings", "default_country") or "All"
	
	default_settings["default_country"] = frappe.db.get_single_value("Pick List Settings", "default_country") or "All"
	default_settings["no_for_manual"] = frappe.db.get_single_value("Pick List Settings", "no_for_manual")
	return default_settings

@frappe.whitelist()
def load_summary(warehouse, source, country):
	to_ship = 0
	to_pick = 0
	rush = 0
	same = 0
	where = ''


	pl_settings = frappe.get_doc("Pick List Settings")
	if source != "All":
		where = f" AND pl.ais_source = '{source}' "
	else:
		# Add disabled sources
		if len(pl_settings.disabled_sources) > 0:
			for row in pl_settings.disabled_sources:
				if row.source != source:
					where += f" AND pl.ais_source <> '{row.source}'"

	if country != "All":
		where += f" AND (customer_addr.country = '{country}' OR ship_addr.country = '{country}')"

	picklists = frappe.db.sql(f"""
			SELECT
				pl.name, pl.customer, pl.is_rush, pli.item_code, pli.qty
			FROM
				`tabPick List Item` AS pli
			LEFT JOIN
				`tabPick List` AS pl ON pl.name = pli.parent
			LEFT JOIN
				`tabSales Order` AS sales_order ON pli.sales_order = sales_order.name
			LEFT JOIN
				`tabAddress` AS customer_addr ON customer_addr.name = sales_order.customer_address
			LEFT JOIN
				`tabAddress` AS ship_addr ON ship_addr.name = sales_order.shipping_address_name
			WHERE
				pli.warehouse = '{warehouse}' AND pl.docstatus = 1
				AND pl.status in ('Open', 'Partially Picked')
				AND (pl.ais_picked_by IS NULL OR pl.ais_picked_by = '' OR pl.ais_picked_by = '{frappe.session.user}')
				AND sales_order.status <> 'On Hold' {where}""", as_dict=1)
	print("Pick: ", picklists)
	
	customers = []
	orders = []
	shipping_items = []

	for row in pl_settings.shipping_items:
		shipping_items.append(row.item)

	for picklist in picklists:
		if picklist.item_code in shipping_items:
			continue

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
def get_pick_lists(warehouse, country, filters, source, sort_by, sort_order):
	where = ''
	if filters != "":
		where = " AND pl.name LIKE '%{where_f}%'".format(where_f = filters)
	if source != "All":
		where = " AND pl.ais_source = '{source}'".format(source = source)
	else:
		# Get disabled sources
		pl_settings = frappe.get_doc("Pick List Settings")
		if len(pl_settings.disabled_sources) > 0:
			for row in pl_settings.disabled_sources:
				where += f" AND pl.ais_source <> '{row.source}'"

	if country != "All":
		where += f" AND (customer_addr.country = '{country}' OR ship_addr.country = '{country}')"

	location_order = "DESC"
	if sort_by == "locations":
		location_order = sort_order
	elif sort_by == "order_date":
		sort_by = "transaction_date"

	# Get the number after which a Pick List is considered wholesale
	no_for_manual = frappe.db.get_single_value("Pick List Settings", "no_for_manual")

	pick_lists = frappe.db.sql(f"""SELECT
										pl.name, pl.customer, pl.customer_name, pl.is_rush, pli.sales_order,
										COUNT(pli.name) AS qty_item,
										GROUP_CONCAT(item.ifw_location ORDER BY item.ifw_location {location_order} 
											SEPARATOR '<br>') AS locations,
										DATE_FORMAT(sales_order.transaction_date, '%d-%m-%Y') AS order_date,
										pl.status, pl.pl_text
									FROM
										`tabPick List Item` AS pli
									LEFT JOIN
										`tabPick List` AS pl ON pl.name = pli.parent
									LEFT JOIN
										`tabProduct Bundle` AS bundle ON bundle.new_item_code = pli.item_code
									LEFT JOIN
										`tabItem` AS item ON item.name = pli.item_code
									LEFT JOIN
										`tabSales Order` AS sales_order ON sales_order.name = pli.sales_order
									LEFT JOIN
										`tabAddress` AS customer_addr ON customer_addr.name = sales_order.customer_address
									LEFT JOIN
										`tabAddress` AS ship_addr ON ship_addr.name = sales_order.shipping_address_name
									WHERE
										pl.docstatus = 1 AND pl.status in ('Open', 'Partially Picked') AND pli.warehouse = '{warehouse}'
										AND (item.is_stock_item = 1 OR bundle.name IS NOT NULL)
										AND sales_order.status <> 'On Hold'
										AND (pl.ais_picked_by IS NULL OR pl.ais_picked_by = '' OR 
										pl.ais_picked_by = '{frappe.session.user}' OR pl.status = 'Partially Picked')
										AND pl.ais_source <> 'Website - GPD'
										{where}
									GROUP BY pl.name, pl.customer, pl.is_rush, pli.sales_order
									HAVING COUNT(pli.name) < {no_for_manual}
									ORDER BY 
										is_rush DESC,
										{sort_by} {sort_order},
										pl.date DESC""", 
								as_dict=1)

	# Add totes for partially picked items
	for pick_list in pick_lists:
		if pick_list["status"] == "Partially Picked":
			tote = frappe.db.get_value("Picklist Tote Item", {"pick_list": pick_list["name"]}, "parent")
			pick_list["tote"] = tote if tote else ""
	return pick_lists

@frappe.whitelist()
def get_items(pick_list="STO-PICK-2024-00101", warehouse="W01-WHS-Active Stock - ICL", user="Administrator", tote="TOTEA03"):
	is_being_picked = frappe.db.get_value('Pick List', pick_list, 'ais_picked_by')
	shipped_items = frappe.db.sql("""SELECT item FROM `tabPick List Shipping Item`""", as_dict=1)
	not_include = ""
	if shipped_items and len(shipped_items):
		not_include = " AND pli.item_code not in  ("
		i = 0
		for row in shipped_items:
			i = i+1
			not_include += f"'{row.item}'"
			if len(shipped_items) != i:
				not_include += ","
		not_include += ") "
	if is_being_picked is None or is_being_picked == '' or is_being_picked == frappe.session.user:
		items = frappe.db.sql("""SELECT
										pli.name, pli.parent AS pick_list, pli.item_code, pli.item_name, item.image,
										pli.ifw_location AS locations, pli.qty, bin.actual_qty,
										CASE 
											WHEN bundle.name IS NOT NULL THEN 1 
											ELSE 0 
										END AS is_product_bundle
									FROM
										`tabPick List Item` AS pli
									LEFT JOIN
										`tabItem` AS item ON item.item_code = pli.item_code
									LEFT JOIN
										`tabProduct Bundle` AS bundle ON bundle.new_item_code = item.name
									LEFT JOIN
										`tabBin` AS bin ON bin.item_code = pli.item_code AND bin.warehouse = %(warehouse)s
									WHERE
										pli.parent = %(pick_list)s
										""" + not_include + """
									ORDER BY pli.ifw_location
									""", {"warehouse": warehouse, "pick_list": pick_list}, as_dict=1)
		
		partially_picked = []
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

			# Load partially picked items
			picked = frappe.db.exists("Picklist Tote Item", 
							{"pick_list": item.pick_list, "pick_list_item": item.name, "item": item.item_code})
			if picked:
				picked_qty, picked_tote = frappe.db.get_value("Picklist Tote Item", picked, ["qty", "parent"])
				partial_item = copy.deepcopy(item)
				partial_item.update({
					"picked_qty": picked_qty,
					"tote": picked_tote
				})
				
				item.update({
					"qty": item.qty - picked_qty,
					"tote": picked_tote
				})
				partially_picked.append(partial_item)

		pl_text = frappe.db.get_value("Pick List", pick_list, "pl_text")
		frappe.db.set_value('Pick List', pick_list, 'ais_picked_by', user)
		doc = {
			"name": items[0].pick_list, 
			"pl_text": pl_text, 
			"items": items,
			"partially_picked": partially_picked
		}
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
def mark_as_picked(picked_items, user, all_items):
	picked_items = json.loads(picked_items)
	all_items = json.loads(all_items)
	pick_lists = []
	totes = []
	delivery_notes = {}
	picklist_items = {}
	all_pick_lists = []
	associated_totes = {}

	for item in all_items:
		item = frappe._dict(item)
		if item.pick_list not in pick_lists:
			all_pick_lists.append(item.pick_list)
			associated_totes[item.pick_list] = item.get("tote")

	for item in picked_items:
		item = frappe._dict(item)
		if item.pick_list not in pick_lists:
			pick_lists.append(item.pick_list)
			picklist_items[item.pick_list] = []
		if item.get('tote') is not None and item.get('tote') not in totes:
			totes.append(item.tote)
		picklist_items[item.pick_list].append(item)
	
	for pick_list in pick_lists:
		doc = frappe.get_doc('Pick List', pick_list)
		status = "Picked"
		non_shipment_items = []
		shipping_items = []

		pl_settings = frappe.get_doc("Pick List Settings", "Pick List Settings")
		for row in pl_settings.shipping_items:
			shipping_items.append(row.item)

		for row in doc.locations:
			if row.item_code not in shipping_items:
				non_shipment_items.append(row)


		if len(picklist_items[pick_list]) != len(non_shipment_items):
			status = "Partially Picked"
		elif len(picklist_items[pick_list]) == len(non_shipment_items):
			for item in picklist_items[pick_list]:
				if item["qty"] > item["picked_qty"]:
					status = "Partially Picked"
					break
		
		picked_by = user
		if status == "Partially Picked":
			picked_by = ""

		doc.update({
			"status": status,
			"ais_picked_by": picked_by
		})
		doc.save()
		#Get associated delivery note
		delivery_note = frappe.db.get_value('Delivery Note', {'pick_list': pick_list}, 'name')
		delivery_notes.update({pick_list: delivery_note})
	#Add to totes
	for tote in totes:
		doc = frappe.get_doc('Picklist Tote', tote)
		doc.tote_items = []
		for item in picked_items:
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

	# Clear pick lists that have not been picked
	for pick_list in all_pick_lists:
		if pick_list not in pick_lists:
			frappe.db.set_value("Pick List", pick_list, "ais_picked_by", "")

			# Clear totes
			if associated_totes.get(pick_list):
				tote = frappe.get_doc("Picklist Tote", associated_totes.get(pick_list))
				tote.update({
					"current_delivery_note": "",
					"tote_items": [],
					"used_by": ""
				})
				tote.save()
	return "Pick List Picked"
	
@frappe.whitelist()
def close_pick_list(pick_list):
	frappe.db.set_value('Pick List', pick_list, 'ais_picked_by', '')
	
@frappe.whitelist()
def clear_totes_picklist(totes, pick_lists):
	totes = json.loads(totes)
	pick_lists = json.loads(pick_lists)
	
	#Clear totes
	if len(totes) > 0:
		where_t = ""
		for tote in totes:
			where_t += ",'{}'".format(tote)
		where_t = where_t[1:]
		frappe.db.sql("""UPDATE `tabPicklist Tote` SET used_by = '' WHERE name IN ({})""".format(where_t))
	
	#Clear pick lists
	if len(pick_lists) > 0:
		where_p = ""
		for pick_list in pick_lists:
			where_p += ",'{}'".format(pick_list)
		where_p = where_p[1:]
		frappe.db.sql("""UPDATE `tabPick List` SET ais_picked_by='' WHERE name IN ({})""".format(where_p))		
	
@frappe.whitelist()
def get_totes(warehouse, pick_lists=""):
	pick_lists = json.loads(pick_lists)
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
	
	# Get totes for partially picked picklists
	partial_totes = []
	for pick_list in pick_lists:
		pl_status = frappe.db.get_value("Pick List", pick_list, "status")
		if pl_status == "Partially Picked":
			tote = frappe.db.get_all("Picklist Tote Item", filters={"pick_list": pick_list}, 
							fields=["parent as tote_name"], page_length=1)
			if len(tote) > 0:
				partial_totes.append({
					"tote_name": tote[0].tote_name,
					"pick_list": pick_list
				})

	return {"totes": totes, "partial_totes": partial_totes}
	
@frappe.whitelist()
def get_tote_items(warehouse, pick_lists, user, totes, assigned_picklists):
	totes = json.loads(totes)
	pick_lists = json.loads(pick_lists)
	pls_list = []
	partially_picked = []
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

	not_include = ""
	if shipped_items and len(shipped_items):
		not_include = "AND pli.item_code NOT IN  ("
		i = 0
		for row in shipped_items:
			i = i+1
			not_include += f"'{row.item}'"
			if len(shipped_items) != i:
				not_include += ","
		not_include += ") "

	items = frappe.db.sql(f"""SELECT 
								pli.name, pli.item_code, pli.item_name, item.image,
								pli.ifw_location AS locations, pli.qty, bin.actual_qty,
								pli.parent AS pick_list, pl.pl_text
							FROM
								`tabPick List Item` AS pli
							LEFT JOIN
								`tabPick List` AS pl ON pl.name = pli.parent
							LEFT JOIN
								`tabItem` AS item ON item.name = pli.item_code
							LEFT JOIN
								`tabBin` AS bin ON bin.item_code = pli.item_code AND bin.warehouse = %(warehouse)s
							WHERE
								pli.parent in {where_pick} {not_include}
							ORDER BY
								pli.ifw_location""",
						{"warehouse": warehouse}, as_dict=1)
	
	#Set the tote items
	assigned_picklists = json.loads(assigned_picklists)
	assigned_totes = {}
	for row in assigned_picklists:
		assigned_totes[row["pick_list"]] = row["tote_name"]

	#SEt the pick list to being picked
	processed_pls = []
	pl_texts = []
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

		# Load partially picked items
		picked = frappe.db.exists("Picklist Tote Item", 
						{"pick_list": item.pick_list, "pick_list_item": item.name, "item": item.item_code})
		if picked:
			picked_qty, tote = frappe.db.get_value("Picklist Tote Item", picked, ["qty", "parent"])
			partial_item = copy.deepcopy(item)
			partial_item.update({
				"picked_qty": picked_qty,
				"tote": tote
			})
			
			item.update({
				"qty": item.qty - picked_qty,
				"tote": tote
			})
			partially_picked.append(partial_item)

		#assign a tote
		item.tote = assigned_totes[item.pick_list]

		# if item.pl_text and item.pl_text is not None:
		if item.pick_list not in processed_pls:
			pl_texts.append({
				"pick_list": item.pick_list,
				"pl_text": item.get("pl_text", ""),
				"tote": item.tote
			})
			processed_pls.append(item.pick_list)

	#Set the totes to being used
	where_t = ''
	for tote in totes:
		where_t += ",'" + tote + "'"
	where_t = where_t[1:]
	query = """UPDATE `tabPicklist Tote` SET used_by=%(user)s WHERE name IN (""" + where_t + """)"""
	frappe.db.sql(query, {"user": user})
	return {"pick_lists": pls_list, "items": items, "partially_picked": partially_picked, "pl_texts": pl_texts}

@frappe.whitelist()
def update_user_filters(user, field_name, field_value):
	"""
	Update a specific default field for a user in Pick List Settings Default
	
	Args:
		user (str): The user to update defaults for (defaults to session user if None)
		field_name (str): The field name to update ('default_warehouse', 'default_location', or 'last_filters')
		field_value (str): The value to set for the field
		
	Returns:
		dict: Status of the update operation
	"""
	if not user:
		user = frappe.session.user
	
	# Check if user exists in the table
	user_exists = frappe.db.exists("Pick List Settings Default", {"user": user})
	
	if not user_exists:
		return
	
	existing_values = frappe.db.get_value("Pick List Settings Default", user_exists, "last_filters")

	if existing_values is None or existing_values == {}:
		existing_values = {}
	
	existing_values = json.loads(existing_values)
	existing_values.update({
		field_name: field_value
	})
	
	frappe.db.set_value("Pick List Settings Default", {"user": user}, "last_filters", json.dumps(existing_values))
		
	return {
		"status": "success", 
		"message": f"Updated {field_name} for user {user}",
		"field_name": field_name,
		"field_value": field_value
	}

@frappe.whitelist()
def update_pl_text(pick_list, pl_text):
	if not frappe.db.exists("Pick List", pick_list):
		frappe.throw("Pick List not found")
	frappe.db.set_value("Pick List", pick_list, "pl_text", pl_text or "")
	return {"status": "success", "pl_text": pl_text or ""}
