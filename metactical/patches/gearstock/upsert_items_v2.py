"""Push the GearStock catalogue (gearstock_items.json) to staging.gearstock through the webhooks.

The items already exist, so Item From Excel skips them and nothing reaches the website. For each
row this adds what is missing and saves the item, which fires the Item / Item Price webhooks:
  - Template / Standalone: the RET - GearStock - USD Item Detail row carrying the slug.
  - Variant / Standalone: the RET - GearStock - USD Item Price, if there is none yet.
Items that are not in the system are skipped and listed in gearstock_items_not_in_erp.csv, next to
the JSON file. Nothing that already exists is overwritten. Progress goes to the "gearstock" log
(sites/<site>/logs/gearstock.log).

Frappe drops webhooks while a patch or migrate is running (run_webhooks returns early on
in_patch / in_migrate), so the patch only enqueues the job; the work runs in a worker. It goes in
batches of 1000, committing and logging progress after each. The webhooks are background jobs, so
how fast they reach the websites is set by the workers, not by this loop. For the run, the Item
and Item Price webhooks are moved to the long queue so they do not hold up the default queue;
they are put back when it finishes (see webhook_queue.py).

When it finishes it queues push_images (pass queue_images=False to skip that).

Safe to re-run by hand: bench --site <site> execute metactical.patches.gearstock.upsert_items.run
"""

import csv
import json
import os

import frappe
from frappe.integrations.doctype.webhook import run_webhooks

from metactical.patches.gearstock import webhook_queue

PRICE_LIST = "RET - GearStock - USD"
BATCH_SIZE = 1000
DATA_FILE = os.path.join(os.path.dirname(__file__), "gearstock_items.json")
MISSING_FILE = os.path.join(os.path.dirname(__file__), "gearstock_items_not_in_erp.csv")
MISSING_COLUMNS = ("item_code", "item_name", "item_type", "template", "slug", "price")
JOB_ID = "gearstock_upsert_items"
WEBHOOK_DOCTYPES = ("Item", "Item Price")

DEV_LIMIT = 2000


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


def run(start=0, queue_images=True):
	logger = frappe.logger("gearstock", allow_site=True)

	with open(DATA_FILE) as f:
		rows = json.load(f)[:DEV_LIMIT]

	# Off the default queue for the run, so its webhook jobs do not hold up everything else.
	webhook_queue.move_to_long(WEBHOOK_DOCTYPES, JOB_ID)
	frappe.db.commit()

	counts = frappe._dict(saved=0, missing=0, price_created=0, slug_added=0, fields_updated=0, failed=0)
	missing, failed = [], []
	logger.info(f"GearStock upsert: starting at {start} of {len(rows)} row(s)")

	for offset in range(int(start), len(rows), BATCH_SIZE):
		for row in rows[offset : offset + BATCH_SIZE]:
			upsert_item(row, counts, missing, failed)

		frappe.db.commit()
		logger.info(f"GearStock upsert: {min(offset + BATCH_SIZE, len(rows))}/{len(rows)} {dict(counts)}")

	write_missing(missing)
	webhook_queue.restore(JOB_ID)

	if queue_images:
		# Queued now, not from patches.txt, so it lands behind every webhook and S3 rename job this
		# run queued: GearStock has the products and the SKUs are final before images go out.
		from metactical.patches.gearstock import push_images

		push_images.start()
	frappe.db.commit()
	logger.info(f"GearStock upsert finished: {dict(counts)}, failed: {failed}, missing items in {MISSING_FILE}")
	frappe.log_error(
		title="GearStock item upsert finished",
		message=json.dumps(
			{"counts": counts, "missing": [row["item_code"] for row in missing], "failed": failed}, indent=1
		),
	)


def write_missing(rows):
	"""The catalogue rows whose item is not in ERPNext, for someone to create or correct."""
	with open(MISSING_FILE, "w", newline="") as f:
		writer = csv.DictWriter(f, fieldnames=MISSING_COLUMNS, extrasaction="ignore")
		writer.writeheader()
		writer.writerows(rows)


def upsert_item(row, counts, missing, failed):
	item_code = row["item_code"]
	if not frappe.db.exists("Item", item_code):
		counts.missing += 1
		missing.append(row)
		return

	frappe.db.savepoint("gearstock_upsert")
	try:
		item = frappe.get_doc("Item", item_code)

		if row.get("slug") and add_item_detail(item, row["slug"], row.get("item_name")):
			counts.slug_added += 1

		if row.get("price") is not None and not item.has_variants and create_item_price(item, row["price"]):
			counts.price_created += 1

		if update_item_fields(item, row):
			counts.fields_updated += 1

		add_website_deduct_qty(item)

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


# catalogue column -> Item field. The retail SKU lives in ifw_retailskusuffix; Item has no
# retail_sku field, so setting that would be silently dropped on save.
ITEM_FIELDS = {"item_group": "item_group", "brand": "brand", "retail_sku": "ifw_retailskusuffix"}


def update_item_fields(item, row):
	"""Set item_group, brand and the retail SKU from the catalogue where they differ.

	Blank catalogue values leave the item alone. Returns True when any value changed. A changed
	retail SKU makes Item.on_update queue the S3 image rename for it (queue_retail_sku_change).
	"""
	changed = False
	for column, field in ITEM_FIELDS.items():
		value = (row.get(column) or "").strip()
		if value and value != (item.get(field) or "").strip():
			item.set(field, value)
			changed = True
	return changed


def add_website_deduct_qty(item):
	"""Add the Website - GearStock row to Website Deduct Qty with qty 0, if it is not there yet."""
	for row in item.get("custom_neb_website_deduct_qty") or []:
		if row.lead_source == "Website - GearStock":
			return False

	item.append("custom_neb_website_deduct_qty", {"lead_source": "Website - GearStock", "qty": 0})
	return True


def add_item_detail(item, slug, item_name=None):
	"""Add the GearStock row with its slug and item name, or fill them in if the slug is blank.
	Returns True when something changed."""
	for detail in item.get("item_detail") or []:
		if detail.price_list == PRICE_LIST:
			if detail.slug:
				return False
			detail.slug = slug
			detail.item_name = item_name
			return True

	item.append("item_detail", {"price_list": PRICE_LIST, "slug": slug, "item_name": item_name})
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
