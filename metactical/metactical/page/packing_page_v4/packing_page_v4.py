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
		frappe.log_error(title="Unable to update item in packing page - v4", message=f"Error updating item {item}: {str(e)}")
		return {"success": False, "message": f"Error updating item: {str(e)}"}

@frappe.whitelist()
def get_all_packed_items(delivery_note):
	packed_items = frappe.db.sql("""
		SELECT
			psi.item_code, psi.item_name, psi.stock_uom, psi.qty, 
			psi.net_weight, psi.parent AS packing_slip,
			i.ifw_retailskusuffix
		FROM
			`tabPacking Slip Item` psi
			JOIN `tabPacking Slip` ON `tabPacking Slip`.name = psi.parent
			JOIN `tabItem` i ON i.item_code = psi.item_code
		WHERE
			`tabPacking Slip`.delivery_note = %s and `tabPacking Slip`.docstatus = 1
	""", delivery_note, as_dict=1)

	packing_slips = frappe.db.get_list("Packing Slip", filters={"delivery_note": delivery_note, "docstatus": 1}, 
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