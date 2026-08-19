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

from metactical.custom_scripts.utils import restock_notification

class ItemInventoryOutput(Document):
	def on_update(self):
		# Metactical Customization: the item is back in stock, so create Restock Email
		# Logs for the matching subscriptions. Fires on both create and update. All
		# logic (and its error handling) lives in restock_notification.py.
		restock_notification.on_item_inventory_output_update(self)

TRANSFER_RULES_CACHE_KEY = "warehouse_transfer_calculation_rules"

def on_sle_update(doc, method):
	# Metactical Customization: skip the (expensive) inventory output
	# recalculation for Stock Entry transfer rows whose source/target
	# warehouse roles aren't whitelisted in Warehouse Transfer Calculation
	# Rule — e.g. Bin -> Bin moves within the same location.
	if is_stock_entry_transfer_skippable(doc):
		return

	# Fetch bins and calculate net available quantities per warehouse
	net_available_bins, last_sle = get_inventory_quantity(doc)

	frappe.enqueue(update_item_inventory_output, item_code=doc.item_code, net_available_bins=net_available_bins, voucher_type=doc.voucher_type, last_sle=last_sle, doc=doc)

def is_stock_entry_transfer_skippable(doc):
	if doc.voucher_type != "Stock Entry" or not doc.voucher_no:
		return False

	decision_cache = get_transfer_decision_cache()
	cache_key = (doc.voucher_no, doc.item_code, doc.warehouse)
	if cache_key in decision_cache:
		return decision_cache[cache_key]

	stock_entry = frappe.get_cached_doc("Stock Entry", doc.voucher_no)

	if stock_entry.purpose != "Material Transfer":
		return False

	warehouse_names = {
		warehouse
		for row in stock_entry.items
		for warehouse in (row.s_warehouse, row.t_warehouse)
		if warehouse
	}
	warehouse_map = get_warehouse_map(warehouse_names)

	# Evaluate every transfer row for this item once, caching both the
	# source and target warehouse decisions so the paired SLE call (each
	# Stock Entry transfer row fires one SLE per warehouse) reads from
	# cache instead of re-scanning stock_entry.items.
	for row in stock_entry.items:
		if row.item_code != doc.item_code or not row.s_warehouse or not row.t_warehouse:
			continue

		calculate = should_calculate_transfer(
			warehouse_map.get(row.s_warehouse), warehouse_map.get(row.t_warehouse)
		)
		decision_cache[(doc.voucher_no, row.item_code, row.s_warehouse)] = not calculate
		decision_cache[(doc.voucher_no, row.item_code, row.t_warehouse)] = not calculate

	# Not part of any transfer row (e.g. plain issue/receipt) -> don't skip.
	return decision_cache.get(cache_key, False)

def get_transfer_decision_cache():
	cache = getattr(frappe.local, "_warehouse_transfer_decision_cache", None)
	if cache is None:
		cache = {}
		frappe.local._warehouse_transfer_decision_cache = cache
	return cache

def get_warehouse_map(warehouse_names):
	if not warehouse_names:
		return {}

	tree = get_warehouse_tree()
	return {name: tree[name] for name in warehouse_names if name in tree}

def should_calculate_transfer(source, target):
	if not source or not target or source.name == target.name:
		return False

	if not source.warehouse_role or not target.warehouse_role:
		return False

	rules = get_transfer_rules()

	same_root = bool(source.root_warehouse) and source.root_warehouse == target.root_warehouse
	root_condition = "Same" if same_root else "Different"

	action = rules.get((source.warehouse_role, target.warehouse_role, root_condition))
	if action is None:
		action = rules.get((source.warehouse_role, target.warehouse_role, "Any"))

	# Default (no matching rule) = Skip.
	return action == "calculate"

def get_transfer_rules():
	local_cache = getattr(frappe.local, "_warehouse_transfer_rules", None)
	if local_cache is not None:
		return local_cache

	rules = frappe.cache().get_value(TRANSFER_RULES_CACHE_KEY, generator=build_transfer_rules)
	frappe.local._warehouse_transfer_rules = rules
	return rules

def build_transfer_rules():
	# Warehouse Transfer Calculation Rule is a Settings (single) doctype; its
	# rules live in the "rules" child table, rows tagged by parenttype.
	rows = frappe.get_all(
		"Warehouse Transfer Calculation Rule Item",
		filters={"parenttype": "Warehouse Transfer Calculation Rule", "enabled": 1},
		fields=["source_role", "target_role", "same_root", "action"],
		order_by="priority asc",
	)

	compiled = {}
	for row in rows:
		key = (row.source_role, row.target_role, row.same_root)
		# First (highest-priority) rule for a given key wins.
		compiled.setdefault(key, row.action.lower())

	return compiled

def get_warehouse_tree():
	# One query for the whole Warehouse tree, fetched fresh at the start of
	# this recalculation (each SLE update runs as its own frappe.enqueue job,
	# i.e. its own request/process, so frappe.local isn't shared across
	# calculations -- no cross-request cache, no invalidation to manage).
	local_cache = getattr(frappe.local, "_warehouse_tree_meta", None)
	if local_cache is not None:
		return local_cache

	rows = frappe.get_all(
		"Warehouse",
		fields=["name", "lft", "rgt", "is_group", "root_warehouse", "warehouse_role"],
	)
	tree = {row.name: row for row in rows}
	frappe.local._warehouse_tree_meta = tree
	return tree

def get_lead_source_configs():
	# Every Lead Source's price list, country, and configured warehouses,
	# fetched in two queries (Lead Source + its SB Warehouse Inventory Sync
	# rows) at the start of this recalculation instead of once per Lead
	# Source per item. Same per-request scoping as get_warehouse_tree.
	local_cache = getattr(frappe.local, "_lead_source_inventory_config", None)
	if local_cache is not None:
		return local_cache

	lead_sources = frappe.get_all(
		"Lead Source",
		fields=["name", "custom_neb_price_list", "neb_country"],
	)

	warehouse_rows = frappe.get_all(
		"SB Warehouse Inventory Sync",
		fields=["parent", "warehouse"],
	)
	warehouses_by_parent = defaultdict(list)
	for row in warehouse_rows:
		warehouses_by_parent[row.parent].append(row.warehouse)

	configs = [
		frappe._dict({
			"name": ls.name,
			"price_list": ls.custom_neb_price_list,
			"country": ls.neb_country,
			"warehouses": warehouses_by_parent.get(ls.name, []),
		})
		for ls in lead_sources
	]
	frappe.local._lead_source_inventory_config = configs
	return configs

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

	if doc.voucher_type == 'Stock Reconciliation':
		# Metactical Customization: ERPNext can re-save older, already-posted
		# Stock Ledger Entries as part of a repost cascade (e.g. after a
		# back-dated correction), which re-fires this hook for that OLDER
		# entry -- and if that re-save's job happens to run after the job
		# for the true latest reconciliation, `qty` above (captured from
		# that older doc) would clobber qoh with a stale value. Re-check the
		# true latest non-cancelled SLE for this item + warehouse at
		# execution time and prefer it, so whichever job runs last always
		# converges on the same correct answer.
		latest_qty_after_transaction = frappe.db.get_value(
			"Stock Ledger Entry",
			{"item_code": doc.item_code, "warehouse": doc.warehouse, "is_cancelled": 0},
			"qty_after_transaction",
			order_by="posting_date desc, posting_time desc, creation desc", 
		)
		if latest_qty_after_transaction is not None:
			qty = flt(latest_qty_after_transaction)

	reserved_qty = frappe.db.get_value("Bin", {"item_code": doc.item_code, "warehouse": doc.warehouse}, "reserved_qty") or 0
	net_available_bins[doc.warehouse] = qty-reserved_qty
 
	return net_available_bins, last_sle

def get_all_bins(item_code):
	# Warehouses whose stock counts toward "active"/sellable quantity: real
	# storage bins and dedicated Active Stock warehouses, identified by
	# warehouse_role rather than a name pattern.
	return frappe.db.sql("""
		SELECT bin.warehouse, bin.actual_qty, bin.reserved_qty
		FROM `tabBin` bin
		JOIN `tabWarehouse` wh ON wh.name = bin.warehouse
		WHERE bin.item_code = %(item_code)s
			AND wh.warehouse_role IN ('Active Stock', 'Bin')
	""", {"item_code": item_code}, as_dict=True)

def get_all_bins_for_product_bundle(parent_item, net_available_bins = {}):
	bundle = frappe.get_doc('Product Bundle', parent_item)
	bundle_items = {x.item_code: x.qty for x in bundle.items}  # Store item qty per bundle unit

	all_bins = frappe.db.sql("""
		SELECT bin.warehouse, bin.item_code, bin.actual_qty, bin.reserved_qty
		FROM `tabBin` bin
		JOIN `tabWarehouse` wh ON wh.name = bin.warehouse
		WHERE bin.item_code IN %(item_codes)s
			AND wh.warehouse_role IN ('Active Stock', 'Bin')
	""", {"item_codes": tuple(bundle_items.keys())}, as_dict=True)

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

def get_warehouse_meta_map(warehouse_names):
	# lft/rgt/is_group for a set of warehouse names, read from the cached
	# warehouse tree instead of a live query per call.
	warehouse_names = [w for w in set(warehouse_names) if w]
	if not warehouse_names:
		return {}

	tree = get_warehouse_tree()
	return {name: tree[name] for name in warehouse_names if name in tree}

def normalize_warehouse_ranges(warehouse_names, warehouse_meta_map=None):
	# Drop any configured warehouse range that's fully nested inside another
	# configured warehouse's range, so a Lead Source that lists both a
	# parent/location warehouse and one of its own children isn't double
	# counted.
	warehouse_names = [w for w in set(warehouse_names) if w]
	if not warehouse_names:
		return []

	meta_map = warehouse_meta_map or get_warehouse_meta_map(warehouse_names)
	rows = [meta_map[name] for name in warehouse_names if name in meta_map]

	rows.sort(key=lambda r: (r.lft, -r.rgt))
	kept = []
	for row in rows:
		if any(k.lft <= row.lft and row.rgt <= k.rgt for k in kept):
			continue
		kept.append(row)

	return kept

def is_in_any_range(item, ranges):
	return any(r.lft <= item.lft <= r.rgt for r in ranges)

def get_subtree_available_qty(item_code, warehouse_names, net_available_bins=None):
	# Sum Bin (actual_qty - reserved_qty) across the union of subtrees
	# rooted at warehouse_names (leaf or group warehouses), letting the
	# database filter the subtree via lft/rgt instead of expanding every
	# descendant warehouse name in Python.
	ranges = normalize_warehouse_ranges(warehouse_names)
	if not ranges:
		return 0

	conditions = []
	params = {"item_code": item_code}
	for i, r in enumerate(ranges):
		conditions.append(f"(wh.lft >= %(lft_{i})s AND wh.rgt <= %(rgt_{i})s)")
		params[f"lft_{i}"] = r.lft
		params[f"rgt_{i}"] = r.rgt

	result = frappe.db.sql(f"""
		SELECT bin.warehouse AS warehouse, SUM(bin.actual_qty - bin.reserved_qty) AS available_qty
		FROM `tabBin` bin
		JOIN `tabWarehouse` wh ON wh.name = bin.warehouse
		WHERE bin.item_code = %(item_code)s
			AND wh.is_group = 0
			AND ({" OR ".join(conditions)})
		GROUP BY bin.warehouse
	""", params, as_dict=True)

	# Bin.actual_qty can momentarily lag behind the SLE that just triggered
	# this recalculation (e.g. a Stock Reconciliation that re-saves its SLE
	# more than once). net_available_bins already carries the corrected,
	# idempotent latest value for the transaction's own warehouse -- prefer
	# it here too, the same way get_inventory_by_country already does.
	seen = set()
	total = 0.0
	for row in result:
		qty = net_available_bins.get(row.warehouse, row.available_qty) if net_available_bins else row.available_qty
		total += flt(qty)
		seen.add(row.warehouse)

	if net_available_bins:
		missing = set(net_available_bins.keys()) - seen
		meta_map = get_warehouse_meta_map(missing)
		for warehouse, qty in net_available_bins.items():
			if warehouse in seen:
				continue
			meta = meta_map.get(warehouse)
			if meta and is_in_any_range(meta, ranges):
				total += flt(qty)

	return total

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
  
		price_list_set = set(price_lists)
		lead_source_configs = [
			config for config in get_lead_source_configs() if config.price_list in price_list_set
		] if price_lists else []

		# Check for existing Item Inventory Output, create new if not found
		item_inventory_output_doc = frappe.db.get_value('Item Inventory Output', {'name': item_code})
		retail_sku = frappe.db.get_value('Item', item_code, 'ifw_retailskusuffix')
		inventory_ouput_data = []

		# Loop through each lead source to calculate quantity to send
		for lead_source_config in lead_source_configs:
			lead_source = lead_source_config.name
			allowed_warehouses = lead_source_config.warehouses

			# Sum total available quantity across allowed warehouses for the lead source.
			# allowed_warehouses may include group/location warehouses, in which case
			# every leaf warehouse in that subtree counts toward the total.
			if not bundle:
				total_available_qty = get_subtree_available_qty(item_code, allowed_warehouses, net_available_bins)
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
  
		total_available_qty = sum(net_available_bins.values()) if not bundle else (min(net_available_bundles) if net_available_bundles else 0)
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

	# Build a mapping: country → configured warehouses (leaf or group/location)
	warehouses_per_country = {}

	for config in get_lead_source_configs():
		if not config.country:
			continue

		warehouses_per_country.setdefault(config.country, []).extend(config.warehouses)

	# Remove duplicates
	for c in warehouses_per_country:
		warehouses_per_country[c] = list(set(warehouses_per_country[c]))

	all_configured_warehouses = {w for ws in warehouses_per_country.values() for w in ws}

	if not all_configured_warehouses:
		frappe.log_error(
			title=f"No warehouses found for country mapping - {item_code}",
			message="No warehouses configured in Lead Sources with country set"
		)
		return []

	warehouse_meta_map = get_warehouse_meta_map(all_configured_warehouses)

	# Normalize each country's configured warehouses into non-overlapping
	# subtree ranges (drops a child range already covered by a configured
	# parent within the same country), plus the union across all countries
	# used to scope the single Bin query below.
	country_ranges = {
		country: normalize_warehouse_ranges(names, warehouse_meta_map)
		for country, names in warehouses_per_country.items()
	}
	all_ranges = normalize_warehouse_ranges(all_configured_warehouses, warehouse_meta_map)

	if not all_ranges:
		frappe.log_error(
			title=f"No warehouses found for country mapping - {item_code}",
			message="No warehouses configured in Lead Sources with country set"
		)
		return []

	if is_bundle:
		# For bundles we already have qty per leaf warehouse from
		# calculate_bundle_qty_per_warehouse; just need each leaf's lft/rgt
		# to place it inside the right country's ranges.
		bundle_warehouse_meta = get_warehouse_meta_map(net_available_bins.keys())
		result = [
			frappe._dict({"warehouse": wh, "lft": meta.lft, "rgt": meta.rgt, "available_qty": qty})
			for wh, qty in net_available_bins.items()
			if (meta := bundle_warehouse_meta.get(wh)) and is_in_any_range(meta, all_ranges)
		]
	else:
		# Regular items: query from Bin, scoped to the configured subtrees
		# via lft/rgt instead of an exact warehouse-name IN list.
		conditions = []
		params = {"item_code": item_code}
		for i, r in enumerate(all_ranges):
			conditions.append(f"(wh.lft >= %(lft_{i})s AND wh.rgt <= %(rgt_{i})s)")
			params[f"lft_{i}"] = r.lft
			params[f"rgt_{i}"] = r.rgt

		query = f"""
			SELECT
				bin.warehouse AS warehouse,
				wh.lft AS lft,
				wh.rgt AS rgt,
				SUM(bin.actual_qty - bin.reserved_qty) AS available_qty
			FROM `tabBin` bin
			JOIN `tabWarehouse` wh ON wh.name = bin.warehouse
			WHERE bin.item_code = %(item_code)s
				AND wh.warehouse_role IN ('Active Stock', 'Bin')
				AND ({" OR ".join(conditions)})
			GROUP BY bin.warehouse, wh.lft, wh.rgt
			ORDER BY available_qty DESC
		"""
		result = frappe.db.sql(query, params, as_dict=1)

		# If SQL returned no rows, fill from net_available_bins
		if not result:
			net_bin_meta = get_warehouse_meta_map(net_available_bins.keys())
			result = [
				frappe._dict({"warehouse": wh, "lft": meta.lft, "rgt": meta.rgt, "available_qty": qty})
				for wh, qty in net_available_bins.items()
				if (meta := net_bin_meta.get(wh)) and is_in_any_range(meta, all_ranges)
			]

	# Reconcile with net_available_bins: the real-time SLE-derived qty for
	# the transaction's own warehouse always takes priority over the Bin
	# snapshot picked up by the query above.
	net_bin_meta = get_warehouse_meta_map(net_available_bins.keys())
	result_by_warehouse = {row.warehouse: row for row in result}

	for wh, qty in net_available_bins.items():
		meta = net_bin_meta.get(wh)
		if not meta or not is_in_any_range(meta, all_ranges):
			continue

		if wh in result_by_warehouse:
			row = result_by_warehouse[wh]
			if is_bundle:
				row.available_qty = qty
			else:
				sql_qty = float(row.available_qty) if row.available_qty else 0
				net_qty = float(qty) if qty else 0

				# Use the higher value
				if sql_qty < net_qty:
					row.available_qty = net_qty
		else:
			new_row = frappe._dict({"warehouse": wh, "lft": meta.lft, "rgt": meta.rgt, "available_qty": qty})
			result.append(new_row)
			result_by_warehouse[wh] = new_row

	inventories_by_country = {}

	for row in result:
		# Corrected qty using net_available_bins always takes priority
		corrected_qty = float(net_available_bins.get(row.warehouse, row.available_qty) or 0)

		# Sum warehouse qty into every country whose configured subtree contains it
		for country, ranges in country_ranges.items():
			if is_in_any_range(row, ranges):
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
