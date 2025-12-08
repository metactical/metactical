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
	all_bins = get_all_bins(doc.item_code)
	net_available_bins = {}
	for bin in all_bins:
		if doc.voucher_type != 'Stock Reconciliation':
			net_available_bins[bin.warehouse] = bin.actual_qty - bin.reserved_qty
	
	if doc.warehouse not in net_available_bins:
		net_available_bins[doc.warehouse] = doc.actual_qty if doc.actual_qty > 0 else 0

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
	if last_sle:
		qty = flt(last_sle.get("qty_after_transaction")) + flt(doc.actual_qty)
	else:
		qty = flt(doc.actual_qty)
  
	reserved_qty = frappe.db.get_value("Bin", {"item_code": doc.item_code, "warehouse": doc.warehouse}, "reserved_qty") or 0 
	net_available_bins[doc.warehouse] = qty-reserved_qty if (qty - reserved_qty) > 0 else 0
 
	frappe.enqueue(update_item_inventory_output, item_code=doc.item_code, net_available_bins=net_available_bins, voucher_type=doc.voucher_type, last_sle=last_sle)

def get_posting_time(doc):
	posting_time_str = None
	if isinstance(doc.posting_time, timedelta):
		new_time = (doc.posting_time - timedelta(seconds=1))
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
	warehouse_item_qty = defaultdict(lambda: defaultdict(int))

	for bin_entry in all_bins:
		item_code = bin_entry["item_code"]
		warehouse = bin_entry["warehouse"]

		warehouse_item_qty[item_code][warehouse] = bin_entry["actual_qty"] - bin_entry["reserved_qty"]

	return {"all_bins": warehouse_item_qty, "bundle_items": bundle_items}

def update_item_inventory_output(item_code, net_available_bins = {}, voucher_type=None, bundle=False, last_sle=None):
	if not voucher_type:
		voucher_type = 'Sales Order'

	try:
		# get price lists from the item price list
		price_lists = frappe.get_all(
			'Item Price', 
			filters={'item_code': item_code}, 
			pluck="price_list"
		)
  
		if not price_lists:
			return
  
		net_available_bundles = []
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
		# lead_sources_in_website_deduct_qty = [x.lead_source for x in website_deduct_qty]
		lead_sources = frappe.get_all('Lead Source', pluck='name', filters={"custom_neb_price_list": ["in", price_lists]})

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
		inventories_by_country = get_inventory_by_country(item_code, last_sle, net_available_bins)

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
					all_bins = get_all_bins_for_product_bundle(parent_item)
					update_item_inventory_output(parent_item, all_bins, voucher_type, bundle=True)
		
	except Exception as e:
		frappe.log_error(title=f"Inventory Update ({voucher_type}) - {item_code}", message=frappe.get_traceback())
		frappe.db.rollback()
  
def get_inventory_by_country(item_code, last_sle=None, net_available_bins={}):
	filters = {"item_code": item_code}
 	
	# Fetch all Lead Sources that have a country set
	lead_sources = frappe.get_all('Lead Source', filters={"neb_country": ["is", "set"]}, pluck='name')
	warehouses_per_country = {}
	
	# Build a mapping: country → list of warehouses
	for lead_source in lead_sources:
		lead_source_doc = frappe.get_cached_doc('Lead Source', lead_source)
		
		# Extract warehouses from lead source
		warehouses = [wh.warehouse for wh in lead_source_doc.custom_neb_sb_warehouse_inventory_sync]
		
		# Group warehouses under their country
		if lead_source_doc.neb_country in warehouses_per_country:
			warehouses_per_country[lead_source_doc.neb_country].extend(warehouses)
		else:
			warehouses_per_country[lead_source_doc.neb_country] = warehouses
   
	# Remove duplicate warehouses per country
	for country, warehouses in warehouses_per_country.items():
		warehouses_per_country[country] = list(set(warehouses))

	all_warehouses = tuple()
	for country, warehouses in warehouses_per_country.items():	
		for warehouse in warehouses:
			all_warehouses += (warehouse,)
 
	# Add to SQL filters
	filters["all_warehouses"] = all_warehouses

	query = """
		SELECT 
			warehouse,
			SUM(bin.actual_qty - bin.reserved_qty) as available_qty
		FROM 
			`tabBin` bin
		INNER JOIN 
			`tabWarehouse` w ON bin.warehouse = w.name
		WHERE 
			bin.item_code = %(item_code)s AND w.name IN %(all_warehouses)s
		GROUP BY 
			warehouse
		ORDER BY 
			available_qty DESC
	"""

	result = frappe.db.sql(query, filters, as_dict=1)
 	
	inventories_dict = []
	inventories_by_country = {}	

	for row in result:  
		warehouse = row.warehouse
		available_qty = row.available_qty
  
		# If this is the warehouse from last_sle, apply net_available_bins override
		if last_sle and warehouse == last_sle.get("warehouse"):
			available_qty = net_available_bins.get(warehouse, available_qty)
			
		# Add available quantities into country-level totals
		for country, warehouses in warehouses_per_country.items():
			if warehouse in warehouses:
				if country in inventories_by_country:
					inventories_by_country[country] += available_qty
				else:
					inventories_by_country[country] = available_qty
	
	# Convert aggregated country data into Inventory Per Country docs
	for country, qty in inventories_by_country.items():
		row_data = {
			"doctype": "Inventory Per Country",
			"country": country,
			"qty":	qty
		}
		
		inventory_doc = frappe.new_doc("Inventory Per Country")
		inventory_doc.update(row_data)
		inventories_dict.append(inventory_doc)
  
	return inventories_dict

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
