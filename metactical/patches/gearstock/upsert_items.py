"""Push the GearStock catalogue (gearstock_items.json) to staging.gearstock through the webhooks.

The items already exist, so Item From Excel skips them and nothing reaches the website. For each
row this adds what is missing and saves the item, which fires the Item / Item Price webhooks:
  - Template / Standalone: the RET - GearStock - USD Item Detail row carrying the slug.
  - Variant / Standalone: the RET - GearStock - USD Item Price, if there is none yet.
Items that are not in the system are skipped. Nothing that already exists is overwritten.

Frappe drops webhooks while a patch or migrate is running (run_webhooks returns early on
in_patch / in_migrate), so the patch only enqueues the job; the work runs in a worker. It goes in
batches with a pause between them so the websites are not flooded with requests.

Safe to re-run by hand: bench --site <site> execute metactical.patches.gearstock.upsert_items.run
"""

import json
import os
import time

import frappe
from frappe.integrations.doctype.webhook import run_webhooks

PRICE_LIST = "RET - GearStock - USD"
BATCH_SIZE = 1000
BATCH_DELAY = 15  # seconds between batches
DATA_FILE = os.path.join(os.path.dirname(__file__), "gearstock_items.json")
JOB_ID = "gearstock_upsert_items"


def execute():
	if not frappe.db.exists("Price List", PRICE_LIST):
		return

	frappe.enqueue(
		"metactical.patches.gearstock.upsert_items.run",
		queue="long",
		timeout=24 * 60 * 60,
		job_id=JOB_ID,
		deduplicate=True,
		enqueue_after_commit=True,
	)


def run(start=0):
	with open(DATA_FILE) as f:
		rows = json.load(f)

	counts = frappe._dict(saved=0, missing=0, price_created=0, slug_added=0, fields_updated=0, failed=0)
	missing, failed = [], []

	for offset in range(int(start), len(rows), BATCH_SIZE):
		for row in rows[offset : offset + BATCH_SIZE]:
			upsert_item(row, counts, missing, failed)

		frappe.db.commit()
		print(f"GearStock upsert: {min(offset + BATCH_SIZE, len(rows))}/{len(rows)} {dict(counts)}")

		if offset + BATCH_SIZE < len(rows):
			time.sleep(BATCH_DELAY)

	frappe.log_error(
		title="GearStock item upsert finished",
		message=json.dumps({"counts": counts, "missing": missing, "failed": failed}, indent=1),
	)


def upsert_item(row, counts, missing, failed):
	item_code = row["item_code"]
	if not frappe.db.exists("Item", item_code):
		counts.missing += 1
		missing.append(item_code)
		return

	frappe.db.savepoint("gearstock_upsert")
	try:
		item = frappe.get_doc("Item", item_code)

		if row.get("slug") and add_item_detail(item, row["slug"]):
			counts.slug_added += 1

		if row.get("price") is not None and not item.has_variants and create_item_price(item, row["price"]):
			counts.price_created += 1

		if update_item_fields(item, row):
			counts.fields_updated += 1

		# Without this, ERPNext's update_variants copies the template's item_detail, retail SKU
		# and supplier rows onto every variant.
		item.flags.dont_update_variants = True
		item.save()
		counts.saved += 1
	except Exception:
		frappe.db.rollback(save_point="gearstock_upsert")
		counts.failed += 1
		failed.append(item_code)
		frappe.log_error(title=f"GearStock item upsert failed: {item_code}", message=frappe.get_traceback())


def update_item_fields(item, row):
	"""Overwrite item_group, brand, retail_sku from the catalogue. Returns True when any value was set."""
	changed = False
	for field in ("item_group", "brand", "retail_sku"):
		value = row.get(field)
		if value:
			item.set(field, value)
			changed = True
	return changed


def add_item_detail(item, slug):
	"""Add the GearStock row, or fill its slug if blank. Returns True when something changed."""
	for detail in item.get("item_detail") or []:
		if detail.price_list == PRICE_LIST:
			if detail.slug:
				return False
			detail.slug = slug
			return True

	item.append("item_detail", {"price_list": PRICE_LIST, "slug": slug})
	return True


def create_item_price(item, rate):
	if frappe.db.exists("Item Price", {"item_code": item.name, "price_list": PRICE_LIST}):
		return False

	item_price = frappe.get_doc(
		{
			"doctype": "Item Price",
			"item_code": item.name,
			"price_list": PRICE_LIST,
			"price_list_rate": rate,
		}
	).insert()

	# The website price webhooks listen on on_change, which Frappe never fires for an insert.
	item_price.flags.in_insert = False
	run_webhooks(item_price, "on_change")
	return True
