import frappe

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
	has_permission = frappe.db.exists('Packing Allowed User', {"user": frappe.session.user})
	if not has_permission:
		return False
	else:
		return True
		
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
		frappe.log_error(f"Error updating item {item_name}: {str(e)}")
		return {"success": False, "message": f"Error updating item: {str(e)}"}

@frappe.whitelist()
def get_all_packed_items(delivery_note):
	packed_items = frappe.db.sql("""
		SELECT
			item_code, item_name, stock_uom, qty, net_weight, `tabPacking Slip Item`.parent AS packing_slip
		FROM
			`tabPacking Slip Item`
			JOIN `tabPacking Slip` ON `tabPacking Slip`.name = `tabPacking Slip Item`.parent
		WHERE
			`tabPacking Slip`.delivery_note = %s and `tabPacking Slip`.docstatus = 1
	""", delivery_note, as_dict=1)

	# group the items by packing slip
	packed_items_dict = {}
	for item in packed_items:
		if item.packing_slip not in packed_items_dict:
			packed_items_dict[item.packing_slip] = []
		packed_items_dict[item.packing_slip].append(item)

	frappe.response["items"] = packed_items_dict