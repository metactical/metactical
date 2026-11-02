"""Copy every GearStock item's images from our other websites into S3 and push them to GearStock.

Runs over the templates and standalone items that carry the RET - GearStock - USD Item Detail row
(the catalogue upsert_items loaded). For each one:
  1. sync_images_from_sb pulls its images from every website it is on and copies into S3 whatever
     the bucket does not have yet; files already there are skipped. It saves the S3 Product Image
     Meta Data record without pushing.
  2. The GearStock Lead Source is added to every image on that record, and the record is saved
     again with the push on, which fires the S3 Product Image Meta Data webhook to the websites.
An item whose images all carry GearStock already is not saved again, so a re-run pushes nothing.

Like upsert_items, the patch only enqueues the job: Frappe drops webhooks while a patch is
running. Items go one at a time with a pause between them so the websites are not flooded.

Progress goes to the "gearstock" log (sites/<site>/logs/gearstock.log). When the job finishes,
gearstock_images_report.csv is written next to gearstock_items.json, listing every item that is
missing images on one of its websites or did not reach GearStock.

Safe to re-run by hand: bench --site <site> execute metactical.patches.gearstock.push_images.run
"""

import csv
import json
import os
import time

import frappe

from metactical.custom_scripts.utils.s3_image_api import (
	get_image_sync_flag,
	set_image_sync_flag,
	sync_images_from_sb,
)
from metactical.metactical.doctype.s3_product_image_meta_data.s3_product_image_meta_data import (
	_doc_state,
)

PRICE_LIST = "RET - GearStock - USD"
ITEM_DELAY = 1  # seconds between items
REPORT_FILE = os.path.join(os.path.dirname(__file__), "gearstock_images_report.csv")
JOB_ID = "gearstock_push_images"
GEARSTOCK_COLUMN = "GearStock"


def execute():
	if not lead_source_for(PRICE_LIST):
		return

	frappe.enqueue(
		"metactical.patches.gearstock.push_images.run",
		queue="long",
		timeout=24 * 60 * 60,
		job_id=JOB_ID,
		deduplicate=True,
		enqueue_after_commit=True,
	)


def run(start=0):
	logger = frappe.logger("gearstock", allow_site=True)

	gearstock = lead_source_for(PRICE_LIST)
	if not gearstock:
		logger.error(f"GearStock images: no Lead Source with a domain is mapped to {PRICE_LIST}")
		return

	items = get_items()
	counts = frappe._dict(pushed=0, already_synced=0, no_images=0, busy=0, failed=0)
	report = []
	logger.info(f"GearStock images: starting at {start} of {len(items)} item(s)")

	for index in range(int(start), len(items)):
		item_code = items[index]
		status = push_item(item_code, gearstock, logger)
		counts[status] += 1
		frappe.db.commit()

		row = report_row(item_code, gearstock, status)
		if row:
			report.append(row)

		logger.info(f"GearStock images: {index + 1}/{len(items)} {item_code} {status} {dict(counts)}")

		if index + 1 < len(items):
			time.sleep(ITEM_DELAY)

	write_report(report)
	logger.info(f"GearStock images finished: {dict(counts)}, report at {REPORT_FILE}")
	frappe.log_error(
		title="GearStock image push finished",
		message=json.dumps({"counts": counts, "report": REPORT_FILE}, indent=1),
	)


def get_items():
	"""Templates and standalone items on GearStock. Variants share their template's record."""
	parents = frappe.get_all(
		"Item Detail",
		filters={"parenttype": "Item", "price_list": PRICE_LIST},
		pluck="parent",
		distinct=True,
	)
	if not parents:
		return []
	return frappe.get_all(
		"Item",
		filters={"name": ["in", parents], "variant_of": ["is", "not set"]},
		order_by="name asc",
		pluck="name",
	)


def push_item(item_code, gearstock, logger):
	"""Bring one item's images into S3 and onto GearStock. Returns the counts key it lands on."""
	if get_image_sync_flag(item_code):
		return "busy"

	frappe.db.savepoint("gearstock_push_images")
	try:
		# Raised here so nobody loads images or changes a SKU on this item mid-run;
		# sync_images_from_sb lowers it again when it is done.
		set_image_sync_flag(item_code, "Administrator", reason="Pushing images to GearStock")
		for message in sync_images_from_sb(item_code):
			logger.info(f"GearStock images: {item_code}: {frappe.utils.strip_html(message)}")

		doc = get_record(item_code)
		if not doc or not doc.nat_images:
			return "no_images"

		added = add_site(doc, gearstock)
		if not added:
			return "already_synced"

		doc.nat_skip_website_push = 0
		doc.save(ignore_permissions=True)
		doc.add_comment("Comment", f"Added GearStock to {added} image(s) and pushed to the websites.")
		return "pushed"
	except Exception:
		frappe.db.rollback(save_point="gearstock_push_images")
		frappe.log_error(title=f"GearStock image push failed: {item_code}", message=frappe.get_traceback())
		return "failed"


def get_record(item_code):
	name = frappe.get_all(
		"S3 Product Image Meta Data",
		filters={"nat_product_template": item_code},
		order_by="creation desc",
		limit=1,
		pluck="name",
	)
	return frappe.get_doc("S3 Product Image Meta Data", name[0]) if name else None


def add_site(doc, site):
	"""Tag every image on the record with `site`. Returns how many images were tagged."""
	added = 0
	for (sku, order, role), image in _doc_state(doc)["images"].items():
		if site in image["sites"]:
			continue
		doc.append("nat_sites", {"nat_site": site, "nat_sku": sku, "nat_image_order": order, "nat_role": role})
		added += 1
	return added


def report_row(item_code, gearstock, status):
	"""{site: Yes/No, ...} for one item, or None when every website has images and GearStock synced.

	Only the websites the item is listed on get a column value; the others stay blank, since a
	product not sold on a website is not missing images there.
	"""
	sites = {}
	for price_list in frappe.get_all(
		"Item Detail", filters={"parent": item_code, "parenttype": "Item"}, pluck="price_list"
	):
		if price_list == PRICE_LIST:
			continue
		site = lead_source_for(price_list)
		if site:
			sites[site] = "No"

	doc = get_record(item_code)
	if doc:
		for image in _doc_state(doc)["images"].values():
			for site in image["sites"]:
				if site in sites:
					sites[site] = "Yes"

	synced = status in ("pushed", "already_synced")
	if synced and "No" not in sites.values():
		return None

	return {"item_code": item_code, **sites, GEARSTOCK_COLUMN: "Synced" if synced else "Not Synced"}


def write_report(rows):
	sites = sorted({key for row in rows for key in row} - {"item_code", GEARSTOCK_COLUMN})
	with open(REPORT_FILE, "w", newline="") as f:
		writer = csv.DictWriter(f, fieldnames=["item_code", *sites, GEARSTOCK_COLUMN], restval="")
		writer.writeheader()
		writer.writerows(rows)


def lead_source_for(price_list):
	"""Same lookup sync_images_from_sb records images under: Lead Source with a domain set."""
	return frappe.db.get_value(
		"Lead Source",
		{"custom_neb_price_list": price_list, "lead_source_domain": ["is", "set"]},
		"name",
		cache=True,
	)
