import frappe, json

@frappe.whitelist()
def get_delivery_from_tote(tote, warehouse):
	is_tote = frappe.db.exists('Picklist Tote', {"name": tote, "warehouse": warehouse})
	if not is_tote:
		return {"is_tote": False, "delivery_note": None}
	else:
		delivery_note = frappe.db.get_value('Picklist Tote', tote, 'current_delivery_note')
		return {"is_tote": True, "delivery_note": delivery_note}
	
@frappe.whitelist()
def check_to_add_permission():
	has_add_permission = frappe.db.exists('Packing Allowed User', {"user": frappe.session.user, "parentfield": "allowed_user"})
	has_add_multiple_permission = frappe.db.exists('Packing Allowed User', {"user": frappe.session.user, "parentfield": "allowed_user_to_multi_pack"})

	frappe.response["has_add_permission"] = has_add_permission
	frappe.response["has_add_multiple_permission"] = has_add_multiple_permission
		
@frappe.whitelist()
def get_default_warehouse():
	has_warehouse = frappe.db.exists('Packing Default Warehouse', {"user": frappe.session.user})
	if has_warehouse:
		return frappe.db.get_value('Packing Default Warehouse', {"user": frappe.session.user}, 'default_warehouse')
	else:
		return ""
		
@frappe.whitelist()
def set_item_weight(item, values):
	default_uom = frappe.db.get_value("Packing Settings", "Packing Settings", "default_weight_uom")
	frappe.db.set_value("Item", item, "weight_per_unit", weight)
	frappe.db.set_value("Item", item, "weight_uom", default_uom)
	return "OK"

@frappe.whitelist()
def set_item_values(item, values):
	try:
		# Parse the values if they're passed as a string
		if isinstance(values, str):
			values = frappe.parse_json(values)

		# Get the item document
		item_doc = frappe.get_doc("Item", item)

		# Update the item fields if they exist in the values
		if "item_weight" in values:
			default_uom = frappe.db.get_value("Packing Settings", "Packing Settings", "default_weight_uom")
			item_doc.weight_per_unit = float(values["item_weight"])
			item_doc.weight_uom = default_uom
		if "item_length" in values:
			item_doc.ais_shipping_length = float(values["item_length"])
		if "item_width" in values:
			item_doc.ais_shipping_width = float(values["item_width"])
		if "item_height" in values:
			item_doc.ais_shipping_height = float(values["item_height"])

		# Save the document
		item_doc.save(ignore_permissions=True)
		return {"success": True, "message": "Item updated successfully"}

	except Exception as e:
		frappe.log_error(title="Unable to update item in packing page - v4", message=f"Error updating item {item}: {str(e)}")
		return {"success": False, "message": f"Error updating item: {str(e)}"}

@frappe.whitelist()
def get_all_packed_items(delivery_note, stock_entry=None):
	doctype = "STE Packing Slip"
	field = "stock_entry"
	value = stock_entry if stock_entry else delivery_note

	if delivery_note:
		doctype = "Packing Slip"
		field = "delivery_note"

	packed_items = frappe.db.sql(f"""
		SELECT
			psi.item_code, psi.item_name, psi.stock_uom, psi.qty, 
			psi.net_weight, psi.parent AS packing_slip,
			i.ifw_retailskusuffix
		FROM
			`tab{doctype} Item` psi
			JOIN `tab{doctype}` ON `tab{doctype}`.name = psi.parent
			JOIN `tabItem` i ON i.item_code = psi.item_code
		WHERE
			`tab{doctype}`.{field} = %s and `tab{doctype}`.docstatus = 1
		ORDER BY
			`tab{doctype}`.creation ASC
	""", value, as_dict=1)

	packing_slips = frappe.db.get_list(doctype, filters={field: value, "docstatus": 1}, 
									fields=["name", "custom_neb_box_height", "custom_neb_box_length", "custom_neb_box_width", "gross_weight_pkg", "custom_neb_parcel_template", "from_case_no"])
	packing_slips = {pl["name"]: pl for pl in packing_slips}

	# group the items by packing slip
	packed_items_dict = {}
	for item in packed_items:
		if item.packing_slip not in packed_items_dict:
			packed_items_dict[item.packing_slip] = []
		packed_items_dict[item.packing_slip].append(item)

	frappe.response["items"] = packed_items_dict
	frappe.response["packed_packing_slips"] = packing_slips

@frappe.whitelist()
def remove_remaining_items(packing_slips, stock_entry, has_pending_items = False):
	packing_slips = json.loads(packing_slips)
	stock_entry_name = stock_entry

	try:
		if has_pending_items:
			packing_slips = frappe.get_all("STE Packing Slip Item", filters={"parent": ["in", packing_slips]}, fields=["name", "docstatus", "ste_detail", "qty"])
			packed_qty = {}

			for packing_slip in packing_slips:
				if packing_slip.ste_detail in packed_qty:
					packed_qty[packing_slip.ste_detail] += packing_slip.qty
				else:
					packed_qty[packing_slip.ste_detail] = packing_slip.qty

			# Get the packing slip items
			stock_entry_items = frappe.get_all("Stock Entry Detail", filters={"parent": stock_entry}, fields=["item_code", "qty", "name"])
			for ste_item in stock_entry_items:
				if ste_item.name in packed_qty:
					stock_entry_item = frappe.get_doc("Stock Entry Detail", ste_item.name)
					ste_item.qty -= (ste_item.qty -packed_qty[ste_item.name])
					stock_entry_item.qty = ste_item.qty
					stock_entry_item.save()
				else:
					stock_entry_item = frappe.get_doc("Stock Entry Detail", ste_item.name)
					stock_entry_item.delete()
		
		stock_entry = frappe.get_doc("Stock Entry", stock_entry)
		stock_entry.save()
		stock_entry.submit()
		frappe.db.commit()

		frappe.response["success"] = True
		frappe.response["message"] = "Items removed successfully" if has_pending_items else "Stock Entry submitted successfully"

	except Exception as e:
		frappe.log_error(title="Unable to remove remaining items in packing page - v4", message=f"Error removing remaining items: {str(e)}")
		frappe.throw(f"<a href='/app/stock-entry/{stock_entry_name}' target='_blank'>Click here to open <b>{stock_entry_name}</b></a>")
