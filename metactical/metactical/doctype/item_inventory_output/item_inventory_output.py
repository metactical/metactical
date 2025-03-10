# Copyright (c) 2024, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
import sys, time
from frappe.model.document import Document
import time
from collections import defaultdict

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
	
	frappe.enqueue(update_item_inventory_output, item_code=doc.item_code, net_available_bins=net_available_bins, voucher_type=doc.voucher_type,  queue='default')

def get_all_bins(item_code):
	all_bins = frappe.get_all(
		'Bin', 
		filters={'item_code': item_code, "warehouse":["like", "%active stock%"]}, 
		fields=["warehouse", "actual_qty", "reserved_qty"]
	)

	other_active_warehouse_bins = frappe.get_all(
		'Bin', 
		filters={'item_code': item_code, "warehouse":["like", "%activestock%"]}, 
		fields=["warehouse", "actual_qty", "reserved_qty"]
	)

	all_bins.extend(other_active_warehouse_bins)

	return all_bins

def get_all_bins_for_product_bundle(parent_item):
	bundle = frappe.get_doc('Product Bundle', parent_item)
	bundle_items = {x.item_code: x.qty for x in bundle.items}  # Store item qty per bundle unit

	all_bins = frappe.get_all(
		'Bin', 
		filters={'item_code': ["in", list(bundle_items.keys())], "warehouse": ["like", "%active stock%"]}, 
		fields=["warehouse", "item_code", "actual_qty", "reserved_qty"]
	)

	other_active_warehouse_bins = frappe.get_all(
		'Bin', 
		filters={'item_code': ["in", list(bundle_items.keys())], "warehouse": ["like", "%activestock%"]}, 
		fields=["warehouse", "item_code", "actual_qty", "reserved_qty"]
	)

	all_bins.extend(other_active_warehouse_bins)

	# Dictionary to store available quantity of each item per warehouse
	warehouse_item_qty = defaultdict(lambda: defaultdict(int))

	for bin_entry in all_bins:
		warehouse = bin_entry["warehouse"]
		item_code = bin_entry["item_code"]
		available_qty = bin_entry["actual_qty"] - bin_entry["reserved_qty"]
		warehouse_item_qty[warehouse][item_code] += available_qty 

	# Calculate the total available quantity of the bundle per warehouse
	warehouse_bundle_qty = {}
 
	for warehouse, item_qtys in warehouse_item_qty.items():
		min_bundle_qty = float("inf")  # Find the limiting factor
		for item_code, qty in item_qtys.items():
			if item_code in bundle_items:  # Ensure item belongs to the bundle
				min_bundle_qty = min(min_bundle_qty, qty // bundle_items[item_code])

		warehouse_bundle_qty[warehouse] = min_bundle_qty 

	return warehouse_bundle_qty  # Returns a dict {warehouse_name: available_bundle_qty}
	
def update_item_inventory_output(item_code, net_available_bins = {}, voucher_type=None, bundle=False):
	if not voucher_type:
		voucher_type = 'Sales Order'

	try:
		# get price lists from the item price list
		price_lists = frappe.get_all(
			'Item Price', 
			filters={'item_code': item_code}, 
			pluck="price_list"
		)

		if not bundle:
			maintain_stock = frappe.db.get_value('Item', item_code, 'is_stock_item')
			if not maintain_stock:
				return

		if not net_available_bins and not bundle:
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
		item_inventory_output_doc = frappe.db.get_value('Item Inventory Output', {'name': item_code})
		retail_sku = frappe.db.get_value('Item', item_code, 'ifw_retailskusuffix')
		data = []

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

			data.append(item_inventory_output_data)

		# Save changes to Item Inventory Output
		total_available_qty = sum(net_available_bins.values())

		if not item_inventory_output_doc:
			item_inventory_output = frappe.new_doc('Item Inventory Output')
			item_inventory_output.item_code = item_code
			item_inventory_output.qoh = total_available_qty
			item_inventory_output.item_inventory_output_list = data
			try:
				item_inventory_output.insert()
				frappe.db.commit()

			except Exception as e:
				item_inventory_output_doc = frappe.db.get_value('Item Inventory Output', {'item_code': item_code})
				if item_inventory_output_doc:
					update_doc(item_inventory_output_doc, total_available_qty, data, item_code, voucher_type)
		else:
			item_inventory_output = frappe.get_doc('Item Inventory Output', item_inventory_output_doc)
			item_inventory_output.qoh = total_available_qty
			item_inventory_output.item_inventory_output_list = data

			try:
				item_inventory_output.save()
				frappe.db.commit()
			except:
				if item_inventory_output_doc:
					update_doc(item_inventory_output_doc, total_available_qty, data, item_code, voucher_type)

		if not bundle:
			product_bundle_parents = is_product_bundle_item(item_code)
			if product_bundle_parents:
				for parent_item in product_bundle_parents:
					all_bins = get_all_bins_for_product_bundle(parent_item)
					update_item_inventory_output(parent_item, all_bins, voucher_type, bundle=True)
		
	except Exception as e:
		frappe.log_error(title=f"Inventory Update ({voucher_type}) - {item_code}", message=frappe.get_traceback())
		frappe.db.rollback()
  
def update_doc(docname, total_available_qty, data, item_code, voucher_type, round=0):
	try:
		item_inventory_output = frappe.get_doc('Item Inventory Output', docname)
		item_inventory_output.reload()
		item_inventory_output.item_inventory_output_list = data
		item_inventory_output.qoh = total_available_qty
		item_inventory_output.save()
	except Exception as e:
		if round > 2:
			frappe.delete_doc('Item Inventory Output', docname)
			item_inventory_output = frappe.new_doc('Item Inventory Output')
			item_inventory_output.item_code = item_code
			item_inventory_output.qoh = total_available_qty
			item_inventory_output.item_inventory_output_list = data
			item_inventory_output.insert()
			frappe.db.commit()
		else:
			sys.stdout.flush()
			time.sleep(2)
			update_doc(docname, total_available_qty, data, item_code, voucher_type, round+1)

def is_product_bundle_item(item_code):
	product_bundle_items = frappe.get_all(
		'Product Bundle Item',
		filters={'item_code': item_code},
		fields=['name', 'parent']
	)
	
	if not product_bundle_items:
		return None
	
	return list(set([x.parent for x in product_bundle_items]))