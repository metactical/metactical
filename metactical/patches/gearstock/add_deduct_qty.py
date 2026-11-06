"""Set Website Deduct Qty to a single Website - GearStock row, once the images have been pushed.

Any rows already on the item are removed, so a row for another website stops deducting from that
website's stock.

Changing the table is what makes Item.on_update queue the inventory update, so this is the step
that sends inventory to the website. It runs last so GearStock already has the products: the
upsert saves them first, then push_images sends the images, and the last image batch queues this.

Each save also fires the Item webhook again, so each product is sent a second time.

It covers the same catalogue rows as upsert_items_v6. Items not in ERPNext are skipped; the upsert
already lists them. Progress goes to the "gearstock" log (sites/<site>/logs/gearstock.log).

Safe to re-run by hand: bench --site <site> execute metactical.patches.gearstock.add_deduct_qty.run
An item that already has just the GearStock row ends up the same, so no inventory update is queued.
"""

import json
import time

import frappe

from metactical.patches.gearstock import db_retry
from apps.metactical.metactical.patches.gearstock.upsert_items_v7 import load_rows

BATCH_SIZE = 100
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
	logger = frappe.logger("gearstock", allow_site=True)
	rows = load_rows()
	counts = frappe._dict(saved=0, missing=0, failed=0)
	failed = []
	logger.info(f"GearStock deduct qty: starting at {start} of {len(rows)} row(s)")

	for offset in range(int(start), len(rows), BATCH_SIZE):
		for row in rows[offset : offset + BATCH_SIZE]:
			update_item(row["item_code"], counts, failed)

		logger.info(f"GearStock deduct qty: {min(offset + BATCH_SIZE, len(rows))}/{len(rows)} {dict(counts)}")
		time.sleep(10)

	logger.info(f"GearStock deduct qty finished: {dict(counts)}, failed: {failed}")
	frappe.log_error(
		title="GearStock deduct qty finished",
		message=json.dumps({"counts": counts, "failed": failed}, indent=1),
	)


def update_item(item_code, counts, failed):
	if not frappe.db.exists("Item", item_code):
		counts.missing += 1
		return

	try:
		db_retry.run(lambda: save_item(item_code))
		counts.saved += 1
	except Exception:
		db_retry.rollback_item()
		counts.failed += 1
		failed.append(item_code)
		frappe.log_error(title=f"GearStock deduct qty failed: {item_code}", message=frappe.get_traceback())


def save_item(item_code):
	item = frappe.get_doc("Item", item_code)
	add_website_deduct_qty(item)

	# Without this, ERPNext's update_variants copies the template's item_detail, retail SKU
	# and supplier rows onto every variant.
	item.flags.dont_update_variants = True
	item.save()
	frappe.db.commit()


def add_website_deduct_qty(item):
	"""Remove any rows in Website Deduct Qty and add the Website - GearStock row with qty 0."""

	if item.get("custom_neb_website_deduct_qty"):
		item.custom_neb_website_deduct_qty = []
		return

	item.append("custom_neb_website_deduct_qty", {"lead_source": "Website - GearStock", "qty": 0})
