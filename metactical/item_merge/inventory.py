"""Put a merged item's stock back in step, and the numbers the websites read from it.

A merge moves an old variant's stock ledger onto the new one, and ERPNext's own
`recalculate_bin_qty` rebuilds the Bins as part of the rename. What it does not put back is the
**Item Inventory Output** record: `CustomItem.before_rename` deletes both the old item's and the new
item's, because `item_code` is that doctype's autoname *and* unique, so the rename would collide on
it. The delete is correct; nothing was putting it back.

So after the pairs are merged, each surviving item gets its Bins recalculated and its inventory
output rebuilt from its newest Stock Ledger Entry - the same call the SLE hook makes, so the result
is the record the rest of the system expects rather than a thinner one written here.
"""
import frappe


def _latest_sle(item_code):
	"""The newest uncancelled ledger row for this item, as a document."""
	name = frappe.get_all("Stock Ledger Entry",
						  filters={"item_code": item_code, "is_cancelled": 0},
						  order_by="posting_date desc, posting_time desc, creation desc",
						  limit=1, pluck="name")
	return frappe.get_doc("Stock Ledger Entry", name[0]) if name else None


def settle(item_codes, log=None):
	"""Recalculate Bins and rebuild the Item Inventory Output for these items.

	Returns {"bins", "outputs", "skipped", "failed", "notes"}. Never raises: the merge itself is
	done by the time this runs, and a stock repost that fails is a thing to report and retry, not a
	reason to fail a job that already moved the ledger.
	"""
	log = log or (lambda m: None)
	counts = {"bins": 0, "outputs": 0, "skipped": 0, "failed": 0}
	notes = []

	# recalculate_bin_qty turns allow_negative_stock on and back off again - but not in a finally,
	# so a repost that raises leaves it on for the whole site. It is called here in a loop that
	# deliberately carries on past failures, so the setting is put back here whatever happens.
	negative_before = frappe.db.get_single_value("Stock Settings", "allow_negative_stock")
	try:
		_settle_each(item_codes, counts, notes, log)
	finally:
		if frappe.db.get_single_value("Stock Settings", "allow_negative_stock") != negative_before:
			frappe.db.set_single_value("Stock Settings", "allow_negative_stock", negative_before)
			frappe.db.commit()
			log("inventory: put allow_negative_stock back to {0}".format(negative_before))

	log("inventory: {0} item(s) recalculated, {1} output(s) rebuilt, {2} skipped, {3} failed".format(
		counts["bins"], counts["outputs"], counts["skipped"], counts["failed"]))
	return {**counts, "notes": notes}


def _settle_each(item_codes, counts, notes, log):
	from metactical.metactical.doctype.item_inventory_output.item_inventory_output import (
		get_inventory_quantity, update_item_inventory_output,
	)

	for item_code in dict.fromkeys(c for c in (item_codes or []) if c):
		if not frappe.db.exists("Item", item_code):
			counts["skipped"] += 1
			continue
		try:
			# ERPNext's own override on CustomItem: only_bin=True, so it does not trip the
			# period-closing guard the way repost_actual_qty would.
			frappe.get_doc("Item", item_code).recalculate_bin_qty(item_code)
			frappe.db.commit()
			counts["bins"] += 1
		except Exception as e:
			counts["failed"] += 1
			notes.append("{0}: bins not recalculated ({1})".format(item_code, str(e)[:90]))
			frappe.db.rollback()
			frappe.log_error(title="Item Merge recalculate_bin_qty {0}".format(item_code),
							 message=frappe.get_traceback())
			continue

		sle = _latest_sle(item_code)
		if not sle:
			# Nothing has ever moved for this item, so there is no inventory to publish. The
			# retail SKU is still worth fixing if a record happens to exist.
			counts["skipped"] += 1
			_fix_retail_sku(item_code)
			continue
		try:
			net_available_bins, last_sle = get_inventory_quantity(sle)
			update_item_inventory_output(item_code=item_code, net_available_bins=net_available_bins,
										 voucher_type=sle.voucher_type, last_sle=last_sle, doc=sle)
			_fix_retail_sku(item_code)
			frappe.db.commit()
			counts["outputs"] += 1
		except Exception as e:
			counts["failed"] += 1
			notes.append("{0}: inventory output not rebuilt ({1})".format(item_code, str(e)[:90]))
			frappe.db.rollback()
			frappe.log_error(title="Item Merge inventory output {0}".format(item_code),
							 message=frappe.get_traceback())



def _fix_retail_sku(item_code):
	"""Keep the inventory output's retail SKU the one the item now carries.

	The websites read stock by retail SKU, so an output still holding the pre-merge SKU publishes
	the right quantity against the wrong product.
	"""
	name = frappe.db.get_value("Item Inventory Output", {"item_code": item_code}, "name")
	if not name:
		return
	sku = frappe.db.get_value("Item", item_code, "ifw_retailskusuffix")
	if sku and frappe.db.get_value("Item Inventory Output", name, "ifw_retailskusuffix") != sku:
		frappe.db.set_value("Item Inventory Output", name, "ifw_retailskusuffix", sku,
							update_modified=False)
