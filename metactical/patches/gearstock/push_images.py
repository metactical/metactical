"""Copy every GearStock item's images from Camo into S3 and push them to GearStock.

Runs over the templates and standalone items in gearstock_items.json, the same catalogue
upsert_items_v5 loads (variants share their template's record). Items not in ERPNext are skipped
and listed in the report. For each one:
  1. Its images are loaded from Camo, the same way Load Data From SB does it: files the S3
     bucket does not have yet are copied in, and the images are merged into the item's existing
     S3 Product Image Meta Data record (added or replaced, never removed).
     In the same save, Website - GearStock is added to every image on the record and the push
     is on, which fires the S3 Product Image Meta Data webhook. One save per item.
  2. Only Camo is read. When it has no images, the item is skipped and written to the log and
     the report.
An item whose record would come out the same is not saved, so a re-run pushes nothing.

It is not in patches.txt: upsert_items_v5 queues it as its last step, so the first batch lands in
the default queue behind every Item / Item Price webhook and retail SKU rename the upsert queued.
Run first, it would push images for products GearStock does not have yet, under SKUs that are
about to be renamed. Items go in batches of 1000, like upsert_items_v5, each batch its own job that queues
the next one, so no job runs long enough to time out. There is a SITE_DELAY wait after every
website call so the websites are not flooded. Everything runs on the default queue, the
batches and the S3 Product Image Meta Data webhooks they fire. If an earlier run left those
webhooks on the long queue, they are put back first (see webhook_queue.py).

Progress goes to the "gearstock" log (sites/<site>/logs/gearstock.log). When the job finishes,
gearstock_images_report.csv is written next to gearstock_items.json, listing every item that
did not reach GearStock and why.

When the last batch is done it queues add_deduct_qty, which sends the inventory.

Safe to re-run by hand: bench --site <site> execute metactical.patches.gearstock.push_images.run
To pick up a stopped run, pass the batch start from the log, e.g. --kwargs "{'start': 3000}".
"""

import csv
import json
import os
import time

import frappe

from metactical.custom_scripts.utils.s3_image_api import (
	clear_image_sync_flag,
	get_image_sync_flag,
	import_website_images,
	set_image_sync_flag,
)
from metactical.patches.gearstock import db_retry, webhook_queue

DATA_FILE = os.path.join(os.path.dirname(__file__), "gearstock_items.json")
GEARSTOCK = "Website - GearStock"
# (price list, Lead Source) in the order they are tried. Several Lead Sources share RET - Camo,
# so the Lead Source is named here rather than looked up from the price list.
IMAGE_SOURCES = (
	("RET - Camo", "Website - Camo"),
)
BATCH_SIZE = 1000
BATCH_TIMEOUT = 6 * 60 * 60  # seconds; one batch of 1000 runs about 1-2 hours
SITE_DELAY = 5  # seconds after each website image load
REPORT_FILE = os.path.join(os.path.dirname(__file__), "gearstock_images_report.csv")
JOB_ID = "gearstock_push_images"
COUNT_KEYS = ("pushed", "already_synced", "no_images", "busy", "failed", "not_in_erp")


def start():
	"""Queue the first batch. Called by upsert_items_v5 when it is done, not from patches.txt."""
	if missing_lead_sources():
		frappe.logger("gearstock", allow_site=True).error(
			"GearStock images: not queued, a Lead Source is missing: " + ", ".join(missing_lead_sources())
		)
		return
	enqueue_batch(0)


def enqueue_batch(start, counts=None):
	"""Queue the job for one batch. Each batch queues the next when it is done, so no single job
	comes near a timeout and a stopped run picks up from the batch it was on."""
	frappe.enqueue(
		"metactical.patches.gearstock.push_images.run",
		queue="default",
		timeout=BATCH_TIMEOUT,
		job_id=f"{JOB_ID}_{start}",
		deduplicate=True,
		enqueue_after_commit=True,
		start=start,
		counts=counts,
	)


def run(start=0, counts=None, chain=True):
	"""Process the batch of BATCH_SIZE items from `start`, then queue the next one.

	`counts` carries the running totals from the batches before. Pass chain=False to do just
	this one batch.
	"""
	start = int(start)
	logger = frappe.logger("gearstock", allow_site=True)

	missing = missing_lead_sources()
	if missing:
		logger.error(f"GearStock images: Lead Source not found: {', '.join(missing)}")
		return

	# Webhooks stay on their own queue (default). Only undo a long-queue move an earlier run left.
	webhook_queue.restore(JOB_ID)
	frappe.db.commit()

	items, not_in_erp = get_items()
	counts = frappe._dict({**dict.fromkeys(COUNT_KEYS, 0), **(counts or {})})
	report = []

	if start == 0:
		# A fresh run: the report starts again, with the catalogue items ERPNext does not have.
		write_report([], fresh=True)
		counts.not_in_erp = len(not_in_erp)
		report = [{"item_code": item_code, "status": "not_in_erp", "image_source": ""} for item_code in not_in_erp]
		if not_in_erp:
			logger.warning(f"GearStock images: {len(not_in_erp)} template(s) in {DATA_FILE} are not in ERPNext")

	end = min(start + BATCH_SIZE, len(items))
	logger.info(f"GearStock images: batch {start + 1}-{end} of {len(items)} item(s)")

	for index, item_code in enumerate(items[start:end], start=start):
		status, source = push_item(item_code, logger)
		counts[status] += 1
		# Per item rather than per batch: the S3 copies cannot be rolled back anyway, and the
		# webhook push fires on commit, so a failure later in the batch must not undo it.
		frappe.db.commit()

		if status not in ("pushed", "already_synced"):
			report.append({"item_code": item_code, "status": status, "image_source": source or ""})
		if status == "no_images":
			logger.warning(f"GearStock images: {item_code} skipped, no images on Camo")

		logger.info(
			f"GearStock images: {index + 1}/{len(items)} {item_code} {status}"
			f"{' from ' + source if source else ''}"
		)

	write_report(report)
	logger.info(f"GearStock images: batch done {end}/{len(items)} {dict(counts)}")

	if end < len(items):
		if chain:
			enqueue_batch(end, dict(counts))
			frappe.db.commit()
		return

	webhook_queue.restore(JOB_ID)
	# Last step of the run: adding the deduct qty row is what sends inventory to the website.
	from metactical.patches.gearstock import add_deduct_qty

	add_deduct_qty.start()
	frappe.db.commit()
	logger.info(f"GearStock images finished: {dict(counts)}, report at {REPORT_FILE}")
	frappe.log_error(
		title="GearStock image push finished",
		message=json.dumps({"counts": counts, "report": REPORT_FILE}, indent=1),
	)


def get_items():
	"""The templates and standalone items in gearstock_items.json: (in ERPNext, not in ERPNext).

	A variant row stands for its template, since variants share their template's image record.
	"""
	from metactical.patches.gearstock.upsert_items_v5 import load_rows

	rows = load_rows()

	codes = sorted({row.get("template") or row["item_code"] for row in rows})
	existing = set(frappe.get_all("Item", filters={"name": ["in", codes]}, pluck="name")) if codes else set()
	return [code for code in codes if code in existing], [code for code in codes if code not in existing]


def push_item(item_code, logger):
	"""Bring one item's images into S3 and onto GearStock.

	Returns (counts key, Lead Source the images came from or None).
	"""
	if get_image_sync_flag(item_code):
		return "busy", None

	try:
		# Raised so nobody loads images or changes a SKU on this item mid-run.
		set_image_sync_flag(item_code, "Administrator", reason="Pushing images to GearStock")
		try:
			status, source = load_images(item_code, logger)
		finally:
			clear_image_sync_flag(item_code)
	except Exception:
		status, source = "failed", None
		frappe.log_error(title=f"GearStock image push failed: {item_code}", message=frappe.get_traceback())

	if status == "failed":
		db_retry.rollback_item()
	return status, source


def load_images(item_code, logger):
	"""Load images from the first of IMAGE_SOURCES that has any, in one save that also adds
	GearStock to every image on the record and pushes it.

	Returns (counts key, Lead Source the images came from or None).
	"""
	for price_list, lead_source in IMAGE_SOURCES:
		result = import_website_images(
			item_code,
			{price_list: lead_source},
			extra_sites=[GEARSTOCK],
			push=True,
			skip_unchanged=True,
		)
		for message in result["messages"]:
			logger.info(f"GearStock images: {item_code}: {frappe.utils.strip_html(message)}")

		# Only wait when the website was actually called; an item not listed on it costs nothing.
		if result["requested"]:
			time.sleep(SITE_DELAY)

		if result["error"]:
			return "failed", lead_source
		if result["found"]:
			return ("pushed" if result["saved"] else "already_synced"), lead_source

	return "no_images", None


def write_report(rows, fresh=False):
	"""Add rows to the report; `fresh` starts it again with just the header."""
	new_file = fresh or not os.path.exists(REPORT_FILE)
	with open(REPORT_FILE, "w" if new_file else "a", newline="") as f:
		writer = csv.DictWriter(f, fieldnames=["item_code", "status", "image_source"])
		if new_file:
			writer.writeheader()
		writer.writerows(rows)


def missing_lead_sources():
	names = [GEARSTOCK, *(source[1] for source in IMAGE_SOURCES)]
	return [name for name in names if not frappe.db.exists("Lead Source", name)]
