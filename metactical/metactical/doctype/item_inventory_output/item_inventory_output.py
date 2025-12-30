# Copyright (c) 2024, Techlift Technologies and contributors
# For license information, please see license.txt

import sys
import frappe
import sys
from frappe.model.document import Document
from collections import defaultdict
from erpnext.stock.stock_ledger import get_previous_sle
from frappe.utils import flt
from datetime import datetime, timedelta, time

class ItemInventoryOutput(Document):
	pass

def on_sle_update(doc, method):
	# Fetch bins and calculate net available quantities per warehouse
	net_available_bins, last_sle = get_inventory_quantity(doc)
 
	frappe.enqueue(update_item_inventory_output, item_code=doc.item_code, net_available_bins=net_available_bins, voucher_type=doc.voucher_type, last_sle=last_sle, doc=doc)

def get_posting_time(doc):
	posting_time_str = None
	if isinstance(doc.posting_time, timedelta):
		new_time = (doc.posting_time - timedelta(seconds=2))
		# Wrap around midnight if needed (i.e., 00:00:00 → 23:59:59)
		if new_time < timedelta(0):
			new_time += timedelta(days=1)

		# Convert to string "HH:MM:SS" if needed
		posting_time_str = str(new_time)
		if "." in posting_time_str:  # strip microseconds if present
			posting_time_str = posting_time_str.split(".")[0]
	elif isinstance(doc.posting_time, str):
		# Try to parse with microseconds, fallback if missing
		try:
			t = datetime.strptime(doc.posting_time, "%H:%M:%S.%f")
		except ValueError:
			t = datetime.strptime(doc.posting_time, "%H:%M:%S")

		new_time = (t - timedelta(seconds=1)).time()
		posting_time_str = new_time.strftime("%H:%M:%S")
  
	return posting_time_str

def get_inventory_quantity(doc):
	# subtract 1 second from posting time
	posting_time = get_posting_time(doc) 
	last_sle = get_previous_sle(
		{
			"item_code": doc.item_code,
			"warehouse": doc.warehouse,
			"posting_date": doc.posting_date,
			"posting_time": posting_time,
		}
	) 
 
	all_bins = get_all_bins(doc.item_code)
	net_available_bins = {}
	for bin in all_bins:
		net_available_bins[bin.warehouse] = bin.actual_qty - bin.reserved_qty
	
	if doc.warehouse not in net_available_bins:
		net_available_bins[doc.warehouse] = doc.actual_qty if doc.actual_qty > 0 else 0

	if last_sle and doc.voucher_type != 'Stock Reconciliation':
		qty = flt(last_sle.get("qty_after_transaction")) + flt(doc.actual_qty)
	elif not last_sle and doc:
     
		qty = max(doc.actual_qty if doc.actual_qty else 0, doc.qty_after_transaction if doc.qty_after_transaction else 0)
	else:
		qty = flt(doc.qty_after_transaction)
			
	reserved_qty = frappe.db.get_value("Bin", {"item_code": doc.item_code, "warehouse": doc.warehouse}, "reserved_qty") or 0 
	net_available_bins[doc.warehouse] = qty-reserved_qty
 
	return net_available_bins, last_sle

def get_all_bins(item_code):
	all_bins = frappe.get_all(
		'Bin', 
		filters={'item_code': item_code, "warehouse":["like", "%active stock%"]}, 
		fields=["warehouse", "actual_qty", "reserved_qty"]
	)

	other_active_warehouse_bins = frappe.get_all(
		'Bin', 
		filters={'item_code': item_code, "warehouse":["like", "%-active%"]}, 
		fields=["warehouse", "actual_qty", "reserved_qty"]
	)

	all_bins.extend(other_active_warehouse_bins)

	return all_bins

def get_all_bins_for_product_bundle(parent_item, net_available_bins = {}):
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
	warehouse_item_qty = defaultdict(lambda: defaultdict(int))

	for bin_entry in all_bins:
		item_code = bin_entry["item_code"]
		warehouse = bin_entry["warehouse"]

		warehouse_item_qty[item_code][warehouse] = bin_entry["actual_qty"] - bin_entry["reserved_qty"]
  
	for item in warehouse_item_qty:

		for wh in warehouse_item_qty[item]:
			if net_available_bins.get(wh) is not None and warehouse_item_qty[item][wh] != net_available_bins.get(wh):
				warehouse_item_qty[item][wh] = net_available_bins.get(wh)

	return {"all_bins": warehouse_item_qty, "bundle_items": bundle_items}

def update_item_inventory_output(item_code, net_available_bins = {}, voucher_type=None, bundle=False, last_sle=None, doc=None):
	try:	
		if voucher_type is None:
			return

		# get price lists from the item price list
		price_lists = frappe.get_all(
			'Item Price', 
			filters={'item_code': item_code}, 
			pluck="price_list"
		)
		net_available_bundles = []
		if not bundle:
			maintain_stock = frappe.db.get_value('Item', item_code, 'is_stock_item')
			if not maintain_stock:
				return

		if not net_available_bins and not bundle:
			if voucher_type in ["Item", "Sales Order"]:
				all_bins = get_all_bins(item_code)
				net_available_bins = frappe._dict({x.warehouse: x.actual_qty - x.reserved_qty for x in all_bins})
			else:
				net_available_bins, last_sle = get_inventory_quantity(doc)

		if not net_available_bins:
			return
  
		# Fetch lead sources and map website deduct quantities by lead source
		website_deduct_qty = frappe.get_all(
			'Website Deduct Qty', 
			filters={'parent': item_code}, 
			fields=["lead_source", "qty"]
		)
		website_deduct_qty_dict = frappe._dict({x.lead_source: x.qty for x in website_deduct_qty})
		# lead_sources_in_website_deduct_qty = [x.lead_source for x in website_deduct_qty]
  
		if price_lists:
			lead_sources = frappe.get_all('Lead Source', pluck='name', filters={"custom_neb_price_list": ["in", price_lists]})
		else:
			lead_sources = []

		# Check for existing Item Inventory Output, create new if not found
		item_inventory_output_doc = frappe.db.get_value('Item Inventory Output', {'name': item_code})
		retail_sku = frappe.db.get_value('Item', item_code, 'ifw_retailskusuffix')
		inventory_ouput_data = []

		# Loop through each lead source to calculate quantity to send
		for lead_source in lead_sources:
			allowed_warehouses = frappe.get_all(
				'SB Warehouse Inventory Sync', 
				filters={'parent': lead_source}, 
				pluck="warehouse"
			)

			# Sum total available quantity across allowed warehouses for the lead source
			if not bundle:
				total_available_qty = sum(net_available_bins.get(warehouse, 0) for warehouse in allowed_warehouses)
			else:
				# Initialize variables for bundle calculation
				available_qty = 0
				net_available_bundles_temp = 0

				# Extract bundle items and all bin inventory_ouput_data
				bundle_items = net_available_bins["bundle_items"]
				all_bins = net_available_bins["all_bins"]

				# List to store available bundles per item
				available_bundles = []

				# Loop through each item in all_bins to calculate available bundles
				for item, warehouses in all_bins.items():
					available_qty = 0  # Reset available quantity for each item

					# Sum up available quantity across allowed warehouses
					for warehouse, qty in warehouses.items():
						if warehouse in allowed_warehouses:
							available_qty += qty  # Add quantity only from allowed warehouses

						net_available_bundles_temp += qty  # Track total available quantity

					# Calculate how many full bundles can be made for the item
					available_bundles.append(available_qty // bundle_items[item])
					
					# Track total available bundles across all items
					net_available_bundles.append(net_available_bundles_temp // bundle_items[item])

				# Determine the total available quantity as the minimum possible bundles
				total_available_qty = min(available_bundles)

				# Ensure total_available_qty is non-negative
				total_available_qty = total_available_qty if total_available_qty > 0 else 0

			# Deduct website reserved quantity from the calculated available quantity
			qty_to_deduct = website_deduct_qty_dict.get(lead_source, 0)
			qty_to_send_to_sb = max(0, total_available_qty - qty_to_deduct)

			# Append item inventory output inventory_ouput_data
			item_inventory_output_data = frappe.new_doc('Item Inventory Output List')
			item_inventory_output_data.update({
				"lead_source": lead_source,
				"qty": qty_to_send_to_sb,
				"ifw_retailskusuffix": retail_sku
			})

			# Store the item inventory output inventory_ouput_data
			inventory_ouput_data.append(item_inventory_output_data)

		# Save changes to Item Inventory Output
		total_available_qty = sum(net_available_bins.values()) if not bundle else min(net_available_bundles)
		inventories_by_country = get_inventory_by_country(item_code, last_sle, net_available_bins, doc)

		if not item_inventory_output_doc:
			item_inventory_output = frappe.new_doc('Item Inventory Output')
			item_inventory_output.item_code = item_code
			item_inventory_output.qoh = total_available_qty
			item_inventory_output.item_inventory_output_list = inventory_ouput_data
			item_inventory_output.inventory_per_country = inventories_by_country
			try:
				item_inventory_output.insert()
				frappe.db.commit()

			except Exception as e:
				item_inventory_output_doc = frappe.db.get_value('Item Inventory Output', {'item_code': item_code})
				if item_inventory_output_doc:
					update_doc(item_inventory_output_doc, total_available_qty, inventory_ouput_data, item_code, voucher_type, inventories_by_country)
		else:
			item_inventory_output = frappe.get_doc('Item Inventory Output', item_inventory_output_doc)
			item_inventory_output.qoh = total_available_qty
			item_inventory_output.item_inventory_output_list = inventory_ouput_data
			item_inventory_output.inventory_per_country = inventories_by_country
   
			try:
				item_inventory_output.save()
				frappe.db.commit()

				# check and delete any failed inventory output record if exists
				delete_failed_inventory_output(item_code)
			except:
				
				if item_inventory_output_doc:
					update_doc(item_inventory_output_doc, total_available_qty, inventory_ouput_data, item_code, voucher_type, inventories_by_country)

		if not bundle:
			product_bundle_parents = is_product_bundle_item(item_code)
			if product_bundle_parents:
				for parent_item in product_bundle_parents:
					all_bins = get_all_bins_for_product_bundle(parent_item, net_available_bins)
					update_item_inventory_output(parent_item, all_bins, voucher_type, bundle=True, doc=doc)
		
	except Exception as e:
		frappe.log_error(title=f"Inventory Update ({voucher_type}) - {item_code}", message=frappe.get_traceback())
		frappe.db.rollback()
  
def get_inventory_by_country(item_code, last_sle=None, net_available_bins={}, doc=None):
	filters = {"item_code": item_code}

	# Check if this is a bundle (has nested structure)
	is_bundle = isinstance(net_available_bins, dict) and "all_bins" in net_available_bins and "bundle_items" in net_available_bins
	
	# Convert bundle structure to warehouse quantities
	if is_bundle:
		warehouse_bundle_qty = calculate_bundle_qty_per_warehouse(
			net_available_bins["all_bins"],
			net_available_bins["bundle_items"]
		)
		net_available_bins = warehouse_bundle_qty
	elif doc and not net_available_bins:
		net_available_bins, last_sle = get_inventory_quantity(doc)

	# Fetch Lead Sources that have a country set
	lead_sources = frappe.get_all(
		'Lead Source',
		filters={"neb_country": ["is", "set"]},
		pluck='name'
	)

	warehouses_per_country = {}

	# Build a mapping: country → warehouses
	for lead_source in lead_sources:
		ls = frappe.get_cached_doc('Lead Source', lead_source)
		warehouses = [w.warehouse for w in ls.custom_neb_sb_warehouse_inventory_sync]

		if ls.neb_country not in warehouses_per_country:
			warehouses_per_country[ls.neb_country] = []

		warehouses_per_country[ls.neb_country].extend(warehouses)

	# Remove duplicates
	for c in warehouses_per_country:
		warehouses_per_country[c] = list(set(warehouses_per_country[c]))

	# Build list of all warehouses
	all_warehouses = tuple(
		w for ws in warehouses_per_country.values() for w in ws
	)
	
	if not all_warehouses:
		frappe.log_error(
			title=f"No warehouses found for country mapping - {item_code}",
			message="No warehouses configured in Lead Sources with country set"
		)
		return []
	
	filters["all_warehouses"] = all_warehouses

	# For bundles, skip SQL query and use calculated bundle quantities
	if is_bundle:
		result = [
			frappe._dict({
				"warehouse": wh,
				"available_qty": qty
			})
			for wh, qty in net_available_bins.items()
			if wh in all_warehouses  # Only include warehouses in country mapping
		]
	else:
		# Regular items: query from Bin
		query = """
			SELECT 
				warehouse,
				SUM(bin.actual_qty - bin.reserved_qty) AS available_qty
			FROM `tabBin` bin
			WHERE bin.item_code = %(item_code)s 
				AND bin.warehouse IN %(all_warehouses)s
			GROUP BY warehouse
			ORDER BY available_qty DESC
		"""
		result = frappe.db.sql(query, filters, as_dict=1)

		# If SQL returned no rows, fill from net_available_bins
		if not result:
			result = [
				frappe._dict({
					"warehouse": wh,
					"available_qty": qty
				})
				for wh, qty in net_available_bins.items()
			]

	inventories_by_country = {}
 
	# Check if warehouses in net_available_bins are missing or have different values than result
	for wh in net_available_bins:
		found = False

		for row in result:
			if row.warehouse == wh:
				found = True
				
				# For bundles, always use net_available_bins (calculated bundle qty)
				# For regular items, use the higher value
				if is_bundle:
					row.available_qty = net_available_bins[wh]
				else:
					sql_qty = float(row.available_qty) if row.available_qty else 0
					net_qty = float(net_available_bins[wh]) if net_available_bins[wh] else 0
					
					# Use the higher value
					if sql_qty < net_qty:
						row.available_qty = net_qty

		# If the warehouse was not in result → add it (if in country mapping)
		if not found and wh in all_warehouses:
			result.append(
				frappe._dict({
					"warehouse": wh,
					"available_qty": net_available_bins[wh]
				})
			)

	for row in result:
		warehouse = row.warehouse

		# Corrected qty using net_available_bins always takes priority
		corrected_qty = float(net_available_bins.get(warehouse, row.available_qty) or 0)

		# Sum warehouse qty into its country
		for country, wh_list in warehouses_per_country.items():
			if warehouse in wh_list:
				inventories_by_country[country] = (
					inventories_by_country.get(country, 0) + corrected_qty
				)

	inventories_dict = []

	for country, qty in inventories_by_country.items():
		row_data = {
			"doctype": "Inventory Per Country",
			"country": country,
			"qty": max(0, qty),
		}

		inv_doc = frappe.new_doc("Inventory Per Country")
		inv_doc.update(row_data)
		inventories_dict.append(inv_doc)

	return inventories_dict

def calculate_bundle_qty_per_warehouse(all_bins, bundle_items):
	"""
	Calculate how many complete bundles can be made per warehouse.
	
	Args:
		all_bins: dict of {item_code: {warehouse: qty}}
		bundle_items: dict of {item_code: qty_per_bundle}
		
	Returns:
		dict of {warehouse: bundle_qty}
	"""
	warehouse_bundle_qty = {}
	
	# Get all unique warehouses across all items
	all_warehouses = set()
	for item_warehouses in all_bins.values():
		all_warehouses.update(item_warehouses.keys())
	
	# For each warehouse, calculate how many bundles can be made
	for warehouse in all_warehouses:
		bundle_qty_per_item = []
		
		# For each item in the bundle
		for item_code, qty_per_bundle in bundle_items.items():
			# Get available qty for this item in this warehouse
			available_qty = all_bins.get(item_code, {}).get(warehouse, 0)
			
			# Calculate how many bundles this item can make
			if qty_per_bundle > 0:
				bundles_from_this_item = available_qty // qty_per_bundle
			else:
				bundles_from_this_item = 0
			
			bundle_qty_per_item.append(bundles_from_this_item)
		
		# The warehouse can make as many bundles as the limiting item allows
		warehouse_bundle_qty[warehouse] = min(bundle_qty_per_item) if bundle_qty_per_item else 0
	
	return warehouse_bundle_qty

def delete_failed_inventory_output(item_code):
	failed_inventory_output_exists = frappe.db.exists("Failed Inventory Output", {"item_code": item_code})
	if failed_inventory_output_exists:
		frappe.db.delete("Failed Inventory Output", failed_inventory_output_exists)
		frappe.db.commit()

def update_doc(docname, total_available_qty, inventory_ouput_data, item_code, voucher_type, inventories_by_country):
	try:
		item_inventory_output = frappe.get_doc('Item Inventory Output', docname)
		item_inventory_output.reload()
		item_inventory_output.item_inventory_output_list = inventory_ouput_data
		item_inventory_output.qoh = total_available_qty
		item_inventory_output.inventory_per_country = inventories_by_country
		item_inventory_output.save()
		frappe.db.commit()
		
		# check and delete any failed inventory output record if exists
		delete_failed_inventory_output(item_code)
	except Exception as e:
			frappe.db.rollback()
			delete_failed_inventory_output(item_code)
			failed_inventory_output = frappe.get_doc({
				"doctype": "Failed Inventory Output",
				"item_code": item_code
			})
			failed_inventory_output.insert(ignore_permissions=True)
			frappe.db.commit()

def is_product_bundle_item(item_code):
	product_bundle_items = frappe.db.sql(f"""
		SELECT
			`tabProduct Bundle Item`.name, `tabProduct Bundle Item`.parent
		FROM
			`tabProduct Bundle Item`
		JOIN
			`tabProduct Bundle` ON `tabProduct Bundle`.name = `tabProduct Bundle Item`.parent
		WHERE
			item_code = '{item_code}' and `tabProduct Bundle`.disabled = 0 
	""", as_dict=True)
	
	if not product_bundle_items:
		return None
	
	return list(set([x.parent for x in product_bundle_items]))
