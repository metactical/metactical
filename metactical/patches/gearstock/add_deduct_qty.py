"""Toggle the Website - GearStock row in Website Deduct Qty, once the images have been pushed.

An item with no rows gets the Website - GearStock row (qty 0). An item that already has rows has
them all removed, and the GearStock row is not added back. Either way the table changes, and a
change, adding or removing, is what makes Item.on_update queue the inventory update. Leaving the
row as it is would queue nothing, so this is the step that sends inventory to the website. It runs last so GearStock already has the products: the
upsert saves them first, then push_images sends the images, and the last image batch queues this.

Each save also fires the Item webhook again, so each product is sent a second time.

It covers the same catalogue rows as upsert_items. A row whose item was merged into another item
updates that item, using the map upsert_items saved (gearstock_merged_items.json). When several
rows land on one item, the same row upsert_items picked does it (row_owners): the item's own row,
otherwise the first merged row. Items not in ERPNext are skipped; the upsert
already lists them. Progress goes to the "gearstock" log (sites/<site>/logs/gearstock.log).

Safe to re-run by hand: bench --site <site> execute metactical.patches.gearstock.add_deduct_qty.run
Each run flips the row (added on one run, removed on the next) and sends the inventory again.
"""

import json
import time

import frappe

from metactical.patches.gearstock import db_retry, log, merged_items
from metactical.patches.gearstock.upsert_items import load_rows, row_owners

BATCH_SIZE = 500
JOB_ID = "gearstock_add_deduct_qty"


def start():
	"""Queue the job. Called by push_images when its last batch is done."""
	frappe.enqueue(
		"metactical.patches.gearstock.add_deduct_qty.run",
		queue="default",
		timeout=24 * 60 * 60,
		job_id=JOB_ID,
		deduplicate=True,
		enqueue_after_commit=True,
	)


def run(start=0):
	logger = log.get_logger()
	rows = load_rows()
	mapping = merged_items.get(rows, logger)
	codes = [merged_items.resolve(row["item_code"], mapping) for row in rows]
	# Built over every row so a resumed run picks the same row as upsert_items did.
	owner = row_owners(rows, mapping)
	counts = frappe._dict(saved=0, missing=0, merged_skipped=0, failed=0)
	failed = []
	logger.info(f"[Inventory] Started at row {int(start) + 1} of {len(rows)}")

	for offset in range(int(start), len(rows), BATCH_SIZE):
		for index, row in enumerate(rows[offset : offset + BATCH_SIZE], start=offset + 1):
			code = codes[index - 1]
			if owner[code] != index - 1:
				counts.merged_skipped += 1
				name = code if code == row["item_code"] else f"{row['item_code']} -> {code} (merged)"
				by = owner[code]
				logger.info(
					f"[Inventory] {name}: skipped, {code} is done from row {by + 1} ({rows[by]['item_code']})"
				)
				continue
			update_item(code, counts, failed, logger, f"{index}/{len(rows)}", row["item_code"])

		logger.info(
			f"[Inventory] Batch completed: {min(offset + BATCH_SIZE, len(rows))}/{len(rows)} rows, totals {dict(counts)}"
		)
		time.sleep(10)

	logger.info(f"[Inventory] Completed: totals {dict(counts)}, failed {failed}")
	frappe.log_error(
		title="GearStock deduct qty finished",
		message=json.dumps({"counts": counts, "failed": failed}, indent=1),
	)


def update_item(item_code, counts, failed, logger, position="", row_code=None):
	merged = row_code and row_code != item_code
	label = f"[Inventory] {row_code} -> {item_code} (merged)" if merged else f"[Inventory] {item_code}"
	logger.info(f"{label}: started ({position})")

	if not frappe.db.exists("Item", item_code):
		counts.missing += 1
		logger.warning(f"{label}: skipped, item not found in ERPNext")
		return

	try:
		change = db_retry.run(lambda: save_item(item_code))
		counts.saved += 1
		logger.info(f"{label}: saved successfully, {change}")
	except Exception:
		db_retry.rollback_item()
		counts.failed += 1
		failed.append(item_code)
		frappe.log_error(title=f"GearStock deduct qty failed: {item_code}", message=frappe.get_traceback())
		logger.error(f"{label}: failed, changes rolled back, see the Error Log")


def save_item(item_code):
	"""Update the item's Website Deduct Qty and save. Returns what changed, for the log."""
	item = frappe.get_doc("Item", item_code)
	change = add_website_deduct_qty(item)

	# Without this, ERPNext's update_variants copies the template's item_detail, retail SKU
	# and supplier rows onto every variant.
	item.flags.dont_update_variants = True
	item.save()
	frappe.db.commit()
	return change


def add_website_deduct_qty(item):
	"""Change Website Deduct Qty so the inventory update is queued: remove every row when there
	are any, otherwise add the Website - GearStock row with qty 0.

	Returns what changed, for the log.
	"""

	rows = item.get("custom_neb_website_deduct_qty")
	if rows:
		removed = ", ".join(f"{row.lead_source} (qty {row.qty})" for row in rows)
		item.custom_neb_website_deduct_qty = []
		return f"removed {len(rows)} existing Website Deduct Qty row(s): {removed}"

	item.append("custom_neb_website_deduct_qty", {"lead_source": "Website - GearStock", "qty": 0})
	return "added Website Deduct Qty row: Website - GearStock, qty 0"
