# Copyright (c) 2024, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class ItemInventoryOutput(Document):
	pass

def on_sle_update(doc, method):
	# Fetch bins and calculate net available quantities per warehouse
	all_bins = get_all_bins(doc.item_code)
	net_available_bins = {}
	for bin in all_bins:
		if bin.warehouse == doc.warehouse and doc.voucher_type != 'Stock Reconciliation':
			net_available_bins[bin.warehouse] = bin.actual_qty - bin.reserved_qty + doc.actual_qty
		elif bin.warehouse == doc.warehouse and doc.voucher_type == 'Stock Reconciliation':
			net_available_bins[bin.warehouse] = doc.qty_after_transaction - bin.reserved_qty
		else:
			net_available_bins[bin.warehouse] = bin.actual_qty - bin.reserved_qty

	frappe.enqueue(update_item_inventory_output, item_code=doc.item_code, net_available_bins=net_available_bins, queue='default')

def get_all_bins(item_code):
	all_bins = frappe.get_all(
		'Bin', 
		filters={'item_code': item_code, "warehouse":["like", "%active stock%"]}, 
		fields=["warehouse", "actual_qty", "reserved_qty"]
	)

	return all_bins
	
def update_item_inventory_output(item_code, net_available_bins = {}):
	try:
		# get price lists from the item price list
		price_lists = frappe.get_all(
			'Item Price', 
			filters={'item_code': item_code}, 
			pluck="price_list"
		)

		maintain_stock = frappe.db.get_value('Item', item_code, 'is_stock_item')
		if not maintain_stock:
			return

		if not net_available_bins:
			all_bins = get_all_bins(item_code)
			net_available_bins = frappe._dict({x.warehouse: x.actual_qty - x.reserved_qty for x in all_bins})

		# Fetch lead sources and map website deduct quantities by lead source
		website_deduct_qty = frappe.get_all(
			'Website Deduct Qty', 
			filters={'parent': item_code}, 
			fields=["lead_source", "qty"]
		)
		website_deduct_qty_dict = frappe._dict({x.lead_source: x.qty for x in website_deduct_qty})
		lead_sources_in_website_deduct_qty = [x.lead_source for x in website_deduct_qty]
		lead_sources = frappe.get_all('Lead Source', pluck='name', filters={"custom_neb_price_list": ["in", price_lists]})

		# Check for existing Item Inventory Output, create new if not found
		item_inventory_output = frappe.db.get_value('Item Inventory Output', {'name': item_code})
		if not item_inventory_output:
			item_inventory_output = frappe.new_doc('Item Inventory Output')
			item_inventory_output.item_code = item_code
		else:
			item_inventory_output = frappe.get_doc('Item Inventory Output', item_inventory_output)
			item_inventory_output.item_inventory_output_list = []

		retail_sku = frappe.db.get_value('Item', item_code, 'ifw_retailskusuffix')

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
			qty_to_send_to_sb = max(0, total_available_qty - qty_to_deduct)

			# Append item inventory output data
			item_inventory_output_data = frappe.new_doc('Item Inventory Output List')
			item_inventory_output_data.update({
				"lead_source": lead_source,
				"qty": qty_to_send_to_sb,
				"ifw_retailskusuffix": retail_sku
			})
			item_inventory_output.item_inventory_output_list.append(item_inventory_output_data)

		# Save changes to Item Inventory Output
		total_available_qty = sum(net_available_bins.values())
		item_inventory_output.qoh = total_available_qty
		item_inventory_output.save()
		frappe.db.commit()

	except Exception as e:
		frappe.log_error(title="Item Inventory Output Update Failed", message=frappe.get_traceback())
		frappe.db.rollback()