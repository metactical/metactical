"""Copy every GearStock item's images from Camo into S3 and push them to GearStock.

Runs over the templates and standalone items in gearstock_items.json, the same catalogue
upsert_items_v7 loads (variants share their template's record). Items not in ERPNext are skipped
and listed in the report. For each one:
  1. Its images are loaded from Camo, the same way Load Data From SB does it: files the S3
     bucket does not have yet are copied in, and the images are merged into the item's existing
     S3 Product Image Meta Data record (added or replaced, never removed).
     In the same save, Website - GearStock is added to every image on the record and the push
     is on, which fires the S3 Product Image Meta Data webhook. One save per item.
  2. Only Camo is read. When it has no images, the item is skipped and written to the log and
     the report.
An item whose record would come out the same is not saved, so a re-run pushes nothing, unless
force is on (repush_images_v1), which saves and pushes every record again.
With resave_existing on, an item whose record already has Website - GearStock on its images is
not loaded from Camo: the record is just saved again with the push on, which fires the webhook.
Items without such a record are loaded from Camo as usual. It is off by default.
With load_from_camo off (it is on by default), Camo is never called: items whose record has
GearStock are saved again as above, and every other item is skipped and listed in the report.

It is not in patches.txt: upsert_items_v7 queues it as its last step, so the first batch lands in
the default queue behind every Item / Item Price webhook and retail SKU rename the upsert queued.
Run first, it would push images for products GearStock does not have yet, under SKUs that are
about to be renamed. Items go in batches of 1000, like upsert_items_v7, each batch its own job that queues
the next one, so no job runs long enough to time out. There is a SITE_DELAY wait after every
website call so the websites are not flooded. Everything runs on the default queue, the
batches and the S3 Product Image Meta Data webhooks they fire. If an earlier run left those
webhooks on the long queue, they are put back first (see webhook_queue.py).

Progress goes to the "gearstock" log (sites/<site>/logs/gearstock.log). When the job finishes,
gearstock_images_report.csv is written next to gearstock_items.json, listing every item that
did not reach GearStock and why.

When the last batch is done it queues add_deduct_qty, which sends the inventory, unless
then_deduct is off.

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
from metactical.patches.gearstock import db_retry, log, webhook_queue

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
COUNT_KEYS = (
	"pushed",
	"already_synced",
	"resaved",
	"no_record",
	"no_gearstock",
	"no_camo_detail",
	"camo_not_configured",
	"not_on_camo",
	"camo_unreachable",
	"camo_bad_response",
	"no_images",
	"camo_load_failed",
	"busy",
	"failed",
	"not_in_erp",
)
# Statuses that mean the item reached GearStock (or already had its images there).
SUCCESS = ("pushed", "already_synced", "resaved")
# The reason written next to each status in the report. Every skip has its own status, so the
# report can be filtered by cause.
REASONS = {
	"no_record": "No image metadata record for this item",
	"no_gearstock": "Image metadata record exists but none of its images have Website - GearStock",
	"no_camo_detail": "Item has no RET - Camo item detail row, so Camo was not called",
	"camo_not_configured": "Camo image API or CDN URL is not set up, so Camo was not called",
	"not_on_camo": "Camo does not have this product",
	"camo_unreachable": "Camo could not be reached",
	"camo_bad_response": "Camo returned an error or a response that could not be read",
	"no_images": "Product found on Camo but it has no images",
	"camo_load_failed": "Loading or saving the Camo images failed, see the Error Log",
	"not_in_erp": "Item not found in ERPNext",
	"busy": "Another image sync was in progress for this item",
	"failed": "Unexpected error, see the Error Log",
}
# The result line written to the log for each status.
LOG_RESULTS = {
	"pushed": "completed, images loaded from Camo, metadata record saved and webhook triggered",
	"already_synced": "completed, images loaded from Camo, metadata record unchanged so not saved (no webhook)",
	"resaved": "completed, existing metadata record saved again without loading from Camo, webhook triggered",
	**{status: f"skipped. Reason: {reason}" for status, reason in REASONS.items()},
	"camo_load_failed": "failed, changes rolled back. Reason: " + REASONS["camo_load_failed"],
	"failed": "failed, changes rolled back. Reason: " + REASONS["failed"],
}
# Camo messages from import_website_images, matched on their text, mapped to a status. Checked in
# this order; the first match wins.
CAMO_MESSAGES = (
	("is not listed on it", "no_camo_detail"),
	("No image API configured", "camo_not_configured"),
	("No CDN URL set", "camo_not_configured"),
	("No Lead Source with a Lead Source Domain", "camo_not_configured"),
	("does not have this product", "not_on_camo"),
	("returned no products", "not_on_camo"),
	("could not be reached", "camo_unreachable"),
	("could not read", "camo_bad_response"),
	("returned HTTP", "camo_bad_response"),
)


def start(force=False, then_deduct=True, resave_existing=False, load_from_camo=True):
	"""Queue the first batch. Called by upsert_items_v7 when it is done, and by repush_images_v1."""
	if missing_lead_sources():
		log.get_logger().error(
			"[Image Push] Not queued, Lead Source not found: " + ", ".join(missing_lead_sources())
		)
		return
	enqueue_batch(
		0, force=force, then_deduct=then_deduct, resave_existing=resave_existing, load_from_camo=load_from_camo
	)


def enqueue_batch(start, counts=None, force=False, then_deduct=True, resave_existing=False, load_from_camo=True):
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
		force=force,
		then_deduct=then_deduct,
		resave_existing=resave_existing,
		load_from_camo=load_from_camo,
	)


def run(
	start=0, counts=None, chain=True, force=False, then_deduct=True, resave_existing=False, load_from_camo=True
):
	"""Process the batch of BATCH_SIZE items from `start`, then queue the next one.

	`counts` carries the running totals from the batches before. Pass chain=False to do just
	this one batch. `force` saves and pushes every item's record even when nothing changed, so
	images GearStock missed are sent again. Pass then_deduct=False to stop after the images
	instead of queueing add_deduct_qty. `resave_existing` skips the Camo load for an item whose
	record already has GearStock on it and just saves that record again, which fires the webhook.
	Pass load_from_camo=False to never call Camo: only those records are saved again, and every
	other item is listed in the report as no_record or no_gearstock.
	"""
	start = int(start)
	logger = log.get_logger()

	if start == 0:
		# Queued from a patch, the first batch must not save while migrate is still altering tables.
		from metactical.patches.gearstock.upsert_items_v7 import wait_for_migrate

		wait_for_migrate()

	missing = missing_lead_sources()
	if missing:
		logger.error(f"[Image Push] Stopped, Lead Source not found: {', '.join(missing)}")
		return

	# Webhooks stay on their own queue (default). Only undo a long-queue move an earlier run left.
	webhook_queue.restore(JOB_ID)
	frappe.db.commit()

	items, not_in_erp = get_items()
	counts = frappe._dict({**dict.fromkeys(COUNT_KEYS, 0), **(counts or {})})

	if start == 0:
		# A fresh run: the report starts again, with the catalogue items ERPNext does not have.
		write_report([report_row(item_code, "not_in_erp") for item_code in not_in_erp], fresh=True)
		counts.not_in_erp = len(not_in_erp)
		logger.info(
			f"[Image Push] Run started: {len(items)} item(s) in ERPNext, {len(not_in_erp)} not in ERPNext, "
			f"load_from_camo={load_from_camo}, resave_existing={resave_existing}, force={force}, "
			f"then_deduct={then_deduct}"
		)
		for item_code in not_in_erp:
			logger.warning(f"[Image Push] {item_code}: {LOG_RESULTS['not_in_erp']}")

	end = min(start + BATCH_SIZE, len(items))
	logger.info(f"[Image Push] Batch started: items {start + 1}-{end} of {len(items)}")

	for index, item_code in enumerate(items[start:end], start=start):
		logger.info(f"[Image Push] {item_code}: started ({index + 1}/{len(items)})")
		status, source = push_item(item_code, logger, force, resave_existing, load_from_camo)
		counts[status] += 1
		# Per item rather than per batch: the S3 copies cannot be rolled back anyway, and the
		# webhook push fires on commit, so a failure later in the batch must not undo it.
		frappe.db.commit()

		if status not in SUCCESS:
			# Written per item, so a batch that dies part way still leaves the items it got through.
			write_report([report_row(item_code, status, source)])
		level = logger.info if status in SUCCESS else logger.warning
		if status in ("failed", "camo_load_failed"):
			level = logger.error
		level(f"[Image Push] {item_code}: {LOG_RESULTS[status]}")

	logger.info(f"[Image Push] Batch completed: {end}/{len(items)} items, totals {dict(counts)}")

	if end < len(items):
		if chain:
			enqueue_batch(
				end,
				dict(counts),
				force=force,
				then_deduct=then_deduct,
				resave_existing=resave_existing,
				load_from_camo=load_from_camo,
			)
			frappe.db.commit()
		return

	webhook_queue.restore(JOB_ID)
	if then_deduct:
		# Last step of the run: adding the deduct qty row is what sends inventory to the website.
		from metactical.patches.gearstock import add_deduct_qty

		add_deduct_qty.start()
	frappe.db.commit()
	logger.info(
		f"[Image Push] Completed: totals {dict(counts)}, report at {REPORT_FILE}"
		+ ("" if then_deduct else ", inventory step skipped (then_deduct is off)")
	)
	frappe.log_error(
		title="GearStock image push finished",
		message=json.dumps({"counts": counts, "report": REPORT_FILE}, indent=1),
	)


def get_items():
	"""The templates and standalone items in gearstock_items.json: (in ERPNext, not in ERPNext).

	A variant row stands for its template, since variants share their template's image record.
	"""
	from metactical.patches.gearstock.upsert_items_v7 import load_rows

	rows = load_rows()

	codes = sorted({row.get("template") or row["item_code"] for row in rows})
	existing = set(frappe.get_all("Item", filters={"name": ["in", codes]}, pluck="name")) if codes else set()
	return [code for code in codes if code in existing], [code for code in codes if code not in existing]


def push_item(item_code, logger, force=False, resave_existing=False, load_from_camo=True):
	"""Bring one item's images into S3 and onto GearStock.

	Returns (counts key, Lead Source the images came from or None).
	"""
	if get_image_sync_flag(item_code):
		return "busy", None

	try:
		# Raised so nobody loads images or changes a SKU on this item mid-run.
		set_image_sync_flag(item_code, "Administrator", reason="Pushing images to GearStock")
		try:
			status, source = None, None
			# Without Camo, saving the existing record again is the only way to push.
			if resave_existing or not load_from_camo:
				status = resave_record(item_code, logger)
			# Not resaved: load from Camo, or keep the reason (no_record / no_gearstock) when off.
			if status != "resaved" and load_from_camo:
				status, source = load_images(item_code, logger, force)
		finally:
			clear_image_sync_flag(item_code)
	except Exception:
		status, source = "failed", None
		frappe.log_error(title=f"GearStock image push failed: {item_code}", message=frappe.get_traceback())

	if status in ("failed", "camo_load_failed"):
		db_retry.rollback_item()
	return status, source


def resave_record(item_code, logger):
	"""Save the item's image record again with the push on, when it already has Website - GearStock
	on its images, so the webhook sends them to GearStock without loading anything from Camo.

	Returns "resaved", or why it was not saved: "no_record" (the item has no image record) or
	"no_gearstock" (the record has no image with Website - GearStock).
	"""
	names = frappe.get_all(
		"S3 Product Image Meta Data",
		filters={"nat_product_template": item_code},
		order_by="creation desc",
		limit=1,
		pluck="name",
	)
	if not names:
		return "no_record"

	doc = frappe.get_doc("S3 Product Image Meta Data", names[0])
	if not any(row.nat_site == GEARSTOCK for row in doc.nat_sites):
		return "no_gearstock"

	# A legacy record submitted before it became editable cannot be saved; upsert_upload does the same.
	if doc.docstatus == 1:
		doc.docstatus = 0
	# Cleared, so the webhook condition lets this save through to the website.
	doc.nat_skip_website_push = 0
	doc.save(ignore_permissions=True)
	doc.add_comment(
		"Comment", "Saved again from the GearStock image patch (push_images) to push the images to GearStock."
	)
	logger.info(f"[Image Push] {item_code}: metadata record {doc.name} saved again")
	return "resaved"


def load_images(item_code, logger, force=False):
	"""Load images from the first of IMAGE_SOURCES that has any, in one save that also adds
	GearStock to every image on the record and pushes it.

	Returns (counts key, Lead Source the images came from or None). When no source has images,
	the status says why, from the last source tried (see camo_status).
	"""
	status = "no_images"
	for price_list, lead_source in IMAGE_SOURCES:
		result = import_website_images(
			item_code,
			{price_list: lead_source},
			extra_sites=[GEARSTOCK],
			push=True,
			skip_unchanged=not force,
		)
		for message in result["messages"]:
			logger.info(f"[Image Push] {item_code}: {frappe.utils.strip_html(message)}")

		# Only wait when the website was actually called; an item not listed on it costs nothing.
		if result["requested"]:
			time.sleep(SITE_DELAY)

		if result["error"]:
			return "camo_load_failed", lead_source
		if result["found"]:
			return ("pushed" if result["saved"] else "already_synced"), lead_source
		status = camo_status(result)

	return status, None


def camo_status(result):
	"""Why a Camo load found no images: the first of CAMO_MESSAGES its messages contain, else
	no_images (Camo had the product, with no images)."""
	text = " ".join(frappe.utils.strip_html(message) for message in result["messages"])
	for needle, status in CAMO_MESSAGES:
		if needle in text:
			return status
	return "no_images"


def report_row(item_code, status, source=None):
	return {"item_code": item_code, "status": status, "reason": REASONS.get(status, ""), "image_source": source or ""}


def write_report(rows, fresh=False):
	"""Add rows to the report; `fresh` starts it again with just the header."""
	new_file = fresh or not os.path.exists(REPORT_FILE)
	with open(REPORT_FILE, "w" if new_file else "a", newline="") as f:
		writer = csv.DictWriter(f, fieldnames=["item_code", "status", "reason", "image_source"])
		if new_file:
			writer.writeheader()
		writer.writerows(rows)


def missing_lead_sources():
	names = [GEARSTOCK, *(source[1] for source in IMAGE_SOURCES)]
	return [name for name in names if not frappe.db.exists("Lead Source", name)]
