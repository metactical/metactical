"""Push the GearStock catalogue (gearstock_items.json) to staging.gearstock through the webhooks.

The items already exist, so Item From Excel skips them and nothing reaches the website. For each
row this adds what is missing and saves the item, which fires the Item / Item Price webhooks:
  - Template / Standalone: the RET - GearStock - USD Item Detail row carrying the slug.
  - Template / Standalone: the RET - Camo Item Detail row with the Camo slug, item name and
    description (camo_slug / camo_item_name / camo_description), which push_images loads the
    images from.
  - Variant / Standalone: the RET - GearStock - USD Item Price, if there is none yet.
Items that are not in the system are skipped and listed in gearstock_items_not_in_erp.csv, next to
the JSON file. Nothing that already exists is overwritten. Progress goes to the "gearstock" log
(sites/<site>/logs/gearstock.log).

Frappe drops webhooks while a patch or migrate is running (run_webhooks returns early on
in_patch / in_migrate), so the patch only enqueues the job; the work runs in a worker. The job
waits for the migrate to finish before it starts. It goes in
batches of 1000, committing and logging progress after each. The webhooks are background jobs, so
how fast they reach the websites is set by the workers, not by this loop. Everything runs on the
default queue: the job itself and the webhooks it fires. If an earlier run left the webhooks on
the long queue, they are put back first (see webhook_queue.py).

When it finishes it queues push_images (pass queue_images=False to skip that). Website Deduct Qty
is not touched here: add_deduct_qty does it after the images, because changing that table is what
queues the inventory update.

Safe to re-run by hand: bench --site <site> execute metactical.patches.gearstock.upsert_items_v5.run
"""

import csv
import json
import os
import time

import frappe
from frappe.integrations.doctype.webhook import run_webhooks
from frappe.utils.synchronization import filelock

from metactical.patches.gearstock import db_retry, webhook_queue

PRICE_LIST = "RET - GearStock - USD"
CAMO_PRICE_LIST = "RET - Camo"
BATCH_SIZE = 100
DATA_FILE = os.path.join(os.path.dirname(__file__), "gearstock_items.json")
MISSING_FILE = os.path.join(os.path.dirname(__file__), "gearstock_items_not_in_erp.csv")
MISSING_COLUMNS = ("item_code", "item_name", "item_type", "template", "slug", "price")
JOB_ID = "gearstock_upsert_items"
MIGRATE_WAIT = 60 * 60  # seconds

# DEV ONLY - remove before prod: only the first DEV_TEMPLATES templates that have both a GearStock
# and a Camo slug (so push_images has a Camo page to load their images from), with all their
# variants. Set to None (or 0) to run the whole catalogue.
DEV_TEMPLATES = 1500


def load_rows():
	"""The catalogue rows to run: all of them, or in dev the first DEV_TEMPLATES templates (in
	file order) with both slugs, and every variant that belongs to them. Shared with push_images."""
	with open(DATA_FILE) as f:
		rows = json.load(f)
	if not DEV_TEMPLATES:
		return rows

	templates = []
	for row in rows:
		if (
			row.get("item_type") == "Template"
			and row.get("slug")
			and row.get("camo_slug")
			and row["item_code"] not in templates
		):
			templates.append(row["item_code"])
			if len(templates) == DEV_TEMPLATES:
				break
	keep = set(templates)
	return [row for row in rows if row.get("template") in keep]


def execute():
	if not frappe.db.exists("Price List", PRICE_LIST):
		return

	frappe.enqueue(
		"metactical.patches.gearstock.upsert_items_v5.run",
		queue="default",
		timeout=24 * 60 * 60,
		job_id=JOB_ID,
		deduplicate=True,
		enqueue_after_commit=True,
	)


def wait_for_migrate():
	"""Wait until the migrate that queued this job has finished. Migrate holds this lock from start
	to end. Saving items while it alters tabItem deadlocks, because the save reads the table and
	then asks for a row lock while the ALTER waits for the read to finish."""
	with filelock("bench_migrate", timeout=MIGRATE_WAIT):
		pass


def run(start=0, queue_images=True):
	logger = frappe.logger("gearstock", allow_site=True)

	wait_for_migrate()

	rows = load_rows()

	# Webhooks stay on their own queue (default). Only undo a long-queue move an earlier run left.
	webhook_queue.restore(JOB_ID)
	frappe.db.commit()

	counts = frappe._dict(
		saved=0, missing=0, price_created=0, slug_added=0, camo_added=0, fields_updated=0, failed=0
	)
	missing, failed = [], []
	logger.info(f"GearStock upsert: starting at {start} of {len(rows)} row(s)")

	for offset in range(int(start), len(rows), BATCH_SIZE):
		for row in rows[offset : offset + BATCH_SIZE]:
			upsert_item(row, counts, missing, failed)

		logger.info(f"GearStock upsert: {min(offset + BATCH_SIZE, len(rows))}/{len(rows)} {dict(counts)}")
		time.sleep(10)
	write_missing(missing)

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

	try:
		for key in db_retry.run(lambda: save_row(row)):
			counts[key] += 1
	except Exception:
		db_retry.rollback_item()
		counts.failed += 1
		failed.append(item_code)
		frappe.log_error(title=f"GearStock item upsert failed: {item_code}", message=frappe.get_traceback())


def save_row(row):
	"""Apply one catalogue row and commit. Returns the counts to add, once the item is saved."""
	changes = ["saved"]
	item = frappe.get_doc("Item", row["item_code"])

	if row.get("slug"):
		if add_item_detail(
			item,
			row["slug"],
			row.get("item_name") or row.get("camo_item_name"),
			row.get("camo_description"),
		):
			changes.append("slug_added")

		# Alongside the GearStock row: the Camo row is what the load from SB (push_images)
		# reads to fetch the images and details from the Camo website.
		if row.get("camo_slug") and add_camo_detail(item, row):
			changes.append("camo_added")

	if row.get("price") is not None and not item.has_variants and create_item_price(item, row["price"]):
		changes.append("price_created")

	if update_item_fields(item, row):
		changes.append("fields_updated")

	# Without this, ERPNext's update_variants copies the template's item_detail, retail SKU
	# and supplier rows onto every variant.
	item.flags.dont_update_variants = True
	item.save()
	frappe.db.commit()
	return changes


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


def add_item_detail(item, slug, item_name=None, description=None):
	"""Add the GearStock row with its slug, item name and description. On an existing row, fill
	the slug if it is blank, set the item name whenever it differs from the catalogue (even if the
	slug is already set), and fill the description only if it is blank. The caller passes the Camo
	name when the catalogue has none, and the Camo description. Returns True when something
	changed."""
	for detail in item.get("item_detail") or []:
		if detail.price_list == PRICE_LIST:
			changed = False
			if not detail.slug:
				detail.slug = slug
				changed = True
			if item_name and detail.item_name != item_name:
				detail.item_name = item_name
				changed = True
			if description and not detail.description:
				detail.description = description
				changed = True
			return changed

	item.append(
		"item_detail",
		{"price_list": PRICE_LIST, "slug": slug, "item_name": item_name, "description": description},
	)
	return True


def add_camo_detail(item, row):
	"""Add the RET - Camo row with the Camo slug, item name and description. On an existing row,
	only blank fields are filled: what is already on the item is not overwritten. Returns True
	when something changed."""
	values = {
		"slug": row.get("camo_slug"),
		"item_name": row.get("camo_item_name"),
		"description": row.get("camo_description"),
	}
	for detail in item.get("item_detail") or []:
		if detail.price_list == CAMO_PRICE_LIST:
			changed = False
			for field, value in values.items():
				if value and not detail.get(field):
					detail.set(field, value)
					changed = True
			return changed

	item.append("item_detail", {"price_list": CAMO_PRICE_LIST, **values})
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
