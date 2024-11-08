# Copyright (c) 2024, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class ItemInventoryOutput(Document):
	pass

def on_sle_update(doc, method):
	# Fetch bins and calculate net available quantities per warehouse
	net_available_bins = get_all_bins(doc.item_code)
	for bin in net_available_bins:
		if bin == doc.warehouse:
			net_available_bins[bin] += doc.actual_qty

	frappe.enqueue(update_item_inventory_output, item_code=doc.item_code, net_available_bins=net_available_bins, queue='default')

def get_all_bins(item_code):
	all_bins = frappe.get_all(
		'Bin', 
		filters={'item_code': item_code, "warehouse":["like", "%active stock%"]}, 
		fields=["warehouse", "actual_qty", "reserved_qty"]
	)

	net_available_bins = frappe._dict({x.warehouse: x.actual_qty - x.reserved_qty for x in all_bins})
	return net_available_bins
	
def update_item_inventory_output(item_code, net_available_bins = {}):
	try:
		if not net_available_bins:
			net_available_bins = get_all_bins(item_code)

		# Fetch lead sources and map website deduct quantities by lead source
		website_deduct_qty = frappe.get_all(
			'Website Deduct Qty', 
			filters={'parent': item_code}, 
			fields=["lead_source", "qty"]
		)
		website_deduct_qty_dict = frappe._dict({x.lead_source: x.qty for x in website_deduct_qty})
		lead_sources = frappe.get_all('Lead Source', pluck='name', filters={"name": ["in", website_deduct_qty_dict.keys()]})

		# Check for existing Item Inventory Output, create new if not found
		item_inventory_output = frappe.db.get_value('Item Inventory Output', {'name': item_code})
		if not item_inventory_output:
			item_inventory_output = frappe.new_doc('Item Inventory Output')
			item_inventory_output.item_code = item_code
		else:
			item_inventory_output = frappe.get_doc('Item Inventory Output', item_inventory_output)
			item_inventory_output.item_inventory_output_list = []

		# Loop through each lead source to calculate quantity to send
		for lead_source in lead_sources:
			allowed_warehouses = frappe.get_all(
				'SB Warehouse Inventory Sync', 
				filters={'parent': lead_source}, 
				pluck="warehouse"
			)

			# Sum total available quantity across allowed warehouses for the lead source
			total_available_qty = sum(net_available_bins.get(warehouse, 0) for warehouse in allowed_warehouses)
			qty_to_deduct = website_deduct_qty_dict.get(lead_source, 0)
			qty_to_send_to_sb = max(0, total_available_qty - qty_to_deduct)  # Avoid negative quantities

			# Append item inventory output data
			item_inventory_output_data = frappe.new_doc('Item Inventory Output List')
			item_inventory_output_data.update({
				"lead_source": lead_source,
				"qty": qty_to_send_to_sb
			})
			item_inventory_output.item_inventory_output_list.append(item_inventory_output_data)

		# Save changes to Item Inventory Output
		total_available_qty = sum(net_available_bins.values())
		item_inventory_output.qoh = total_available_qty
		item_inventory_output.save()
		frappe.msgprint('Item Inventory Output Updated')
		frappe.db.commit()

	except Exception as e:
		frappe.log_error(title="Item Inventory Output Update Failed", message=frappe.get_traceback())
		frappe.db.rollback()