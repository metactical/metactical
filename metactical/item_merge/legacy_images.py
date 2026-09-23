"""Keep a legacy product's images before its Storebuilder product is deleted.

A merge consolidates several templates into one and then drops the old products from the
websites. Those products carry the photography - and once the drop has gone through it is gone
from Storebuilder too. The new variants inherit the stock, the ledger and the SKUs; without this
they inherit no pictures.

So, in the job and **immediately before the drop**, each legacy product is asked for its images
one last time, they are pulled into S3, and they are re-pointed at the new variants the merge
just created.

**Why this runs in the job rather than on the Find Template screen.** By the time a merge is
queued the legacy templates are long deleted from ERPNext - `consolidate_templates` removed them
in step 1 - so there is no Item left to read `item_detail` slugs off. What does survive is the
Legacy Website Product register, which carries the slug and the price list, and that is all
`_fetch_sb_product` needs. It is also the truthful moment: the images are taken from the product
that is about to be deleted, not from a snapshot of it taken days earlier.

**How an image finds its new home.** Storebuilder keys images by variant SKU, so the chain is
SKU -> old variant -> new variant. The middle step is the pair's `snapshot`, written by
`merge.merge_pair` before the old item was deleted, which still holds its `ifw_retailskusuffix`.
Anything that cannot be traced that way - an unpaired old variant, a leftover, a SKU no variant
carried - keeps its image with no item code rather than being guessed onto the wrong product.
"""
import json

import frappe

from metactical.item_merge import catalogue

IMAGE_FIELD = "image_apis"


def _configs():
	"""The per-website image API rows, by price list."""
	rows = frappe.get_all("Item Import Validation",
						  filters={"parentfield": IMAGE_FIELD, "enabled": 1}, fields=["*"])
	return {r.price_list: r for r in rows if r.price_list and r.api_url}


def new_item_for_sku(job):
	"""{Storebuilder SKU: the new item code it should point at now}.

	Built from the job's own pairs, which is the mapping the merge already committed to. Both the
	old retail SKU and the old item code are accepted as keys: Storebuilder reports
	`fullRetailSku` for some products and the bare suffix for others, and the two are not always
	the same value.
	"""
	out = {}
	for pair in job.get("pairs") or []:
		if pair.status not in ("Ok", "Skipped") or not pair.new_item:
			continue
		keys = {pair.old_item}
		try:
			snapshot = json.loads(pair.snapshot or "{}").get("doc") or {}
		except ValueError:
			snapshot = {}
		if snapshot.get("ifw_retailskusuffix"):
			keys.add(snapshot["ifw_retailskusuffix"])
		for key in keys:
			if key:
				out[str(key).strip()] = pair.new_item
	return out


def _survivor_rows(template):
	"""The surviving template's own (price list, slug) pairs, from its Item Detail.

	Written there in step 1 from what Storebuilder answered, so by the time the job runs they are
	the slugs the sites are actually serving for this product.
	"""
	if not template or not frappe.db.exists("Item", template):
		return []
	out = []
	for row in frappe.get_doc("Item", template).get("item_detail") or []:
		if row.price_list and (row.slug or "").strip():
			out.append({"product": template, "price_list": row.price_list,
						"slug": row.slug.strip(),
						"lead_source": catalogue.lead_source_for(row.price_list)})
	return out


def _drop_other_records(job, kept):
	"""Remove the image records left over from the templates this merge consolidated away.

	`rename_doc(merge=True)` repoints every Link at the survivor, so a consolidated template's
	S3 Product Image Meta Data comes out of step 1 pointing at the survivor too - a second record
	for the same product, which every reader here picks between by `creation desc` and would
	silently ignore half of. Its images are in `kept` by now.
	"""
	if not kept:
		return 0
	stale = frappe.get_all("S3 Product Image Meta Data",
						   filters={"nat_product_template": job.template, "name": ["!=", kept]},
						   pluck="name")
	legacy = {r.product for r in (job.get("legacy_products") or []) if r.product != job.template}
	if legacy:
		stale += frappe.get_all("S3 Product Image Meta Data",
								filters={"nat_product_template": ["in", sorted(legacy)]},
								pluck="name")
	for name in dict.fromkeys(stale):
		frappe.delete_doc("S3 Product Image Meta Data", name, force=True, ignore_permissions=True)
	return len(dict.fromkeys(stale))


def pull_and_remap(job, log=None):
	"""Pull every legacy product's images into S3 and point them at the new variants.

	Returns {"products", "images", "mapped", "unmapped", "skipped", "failed", "notes"}. Nothing
	here raises: a website that cannot answer costs its own images, not the merge.
	"""
	from metactical.custom_scripts.utils.s3_image_api import (
		_collect_website_images, _fetch_sb_product,
	)
	from metactical.metactical.doctype.s3_product_image_meta_data.s3_product_image_meta_data import (
		_doc_state, upsert_upload,
	)
	from metactical.metactical.page.s3_uploader.s3_uploader import resolve_item_codes

	log = log or (lambda m: None)
	counts = {"products": 0, "images": 0, "mapped": 0, "unmapped": 0, "skipped": 0, "failed": 0,
			  "records_removed": 0}
	notes = []

	# Every product whose images belong under the survivor: the legacy ones about to be dropped,
	# and the survivor's own - its variants' photography is as much part of the consolidated
	# product as theirs, and nothing else gathers it.
	rows = [{"product": r.product, "price_list": r.price_list, "slug": r.slug,
			 "lead_source": r.lead_source}
			for r in (job.get("legacy_products") or [])
			if r.slug and r.price_list and r.product != job.template]
	rows += _survivor_rows(job.template)
	if not rows:
		return {**counts, "notes": notes}

	configs = _configs()
	stats = {"uploaded": set(), "skipped": set(), "errors": 0, "broken_links": 0}

	settings = frappe.get_single("S3 Settings")
	s3_client = settings.get_client()
	bucket = settings.nat_bucket_name

	found = {}
	for row in rows:
		# nat_site is a Link to Lead Source, so a website with none behind it has nowhere to be
		# recorded - and a None in the set would take sorted() down with it further on.
		if not row["lead_source"]:
			counts["skipped"] += 1
			notes.append("{0}: {1} has no Lead Source".format(row["product"], row["price_list"]))
			continue
		config = configs.get(row["price_list"])
		if not config:
			counts["skipped"] += 1
			notes.append("{0}: no image API for {1}".format(row["product"], row["price_list"]))
			continue
		try:
			product, error = _fetch_sb_product(config, row["product"], row["slug"])
			if error or not product:
				counts["skipped"] += 1
				notes.append("{0} on {1}: {2}".format(row["product"], row["price_list"],
													  error or "no product"))
				continue
			hits = _collect_website_images(product, config.cdn_url, s3_client, bucket, stats)
		except Exception as e:
			counts["failed"] += 1
			notes.append("{0} on {1}: {2}".format(row["product"], row["price_list"], str(e)[:120]))
			frappe.log_error(title="Item Merge legacy images {0}".format(row["product"]),
							 message=frappe.get_traceback())
			continue

		counts["products"] += 1
		for key, path in hits.items():
			entry = found.setdefault(key, {"path": path, "sites": set()})
			entry["path"] = path
			# The Lead Source itself, not its domain: nat_site is a Link to Lead Source, and the
			# uploader picks its sites by the same name.
			entry["sites"].add(row["lead_source"])
		log("images {0} on {1}: {2} image row(s)".format(row["product"], row["price_list"],
														len(hits)))

	if not found:
		return {**counts, "notes": notes}

	counts["images"] = len(found)

	# Lay the legacy images over whatever the surviving template already has, rather than
	# replacing it: upsert_upload rebuilds the child tables from what it is given, so anything
	# left out would be dropped.
	merged, override, stored = {}, 0, {}
	existing = frappe.get_all("S3 Product Image Meta Data",
							  filters={"nat_product_template": job.template},
							  order_by="creation desc", limit=1, pluck="name")
	if existing:
		doc = frappe.get_doc("S3 Product Image Meta Data", existing[0])
		override = int(doc.nat_override_full_product or 0)
		state = _doc_state(doc)
		merged = {key: dict(value) for key, value in state["images"].items()}
		stored = {sku: code for sku, code in state["skus"].items() if code}

	for key, hit in found.items():
		entry = merged.setdefault(key, {"path": hit["path"], "sites": frozenset()})
		entry["path"] = hit["path"]
		entry["sites"] = frozenset(entry.get("sites") or frozenset()) | frozenset(hit["sites"])

	# Three sources, weakest first. The lookup matches a Storebuilder SKU to whichever Item carries
	# it as its retail SKU, which is what resolves the surviving template's own variants - they were
	# never merged, so no pair mentions them. Anything set by hand in the uploader beats that. The
	# merge's own pairs beat everything: they are the mapping this job just committed to, and they
	# still hold for an old variant whose retail SKU moved to its new one.
	item_of = resolve_item_codes(sorted({sku for sku, _order, _role in merged}))
	item_of.update(stored)
	item_of.update(new_item_for_sku(job))

	files = []
	for (sku, order, role), entry in merged.items():
		# An untraceable SKU is left unmapped on purpose rather than guessed onto a product.
		item_code = item_of.get(sku)
		if (sku, order, role) in found:
			counts["mapped" if item_code else "unmapped"] += 1
		files.append({"role": role, "order": order, "path": entry["path"],
					  "sites": sorted(entry["sites"]),
					  "skuItems": [{"sku": sku, "item_code": item_code}]})

	kept = upsert_upload(files, override_full_product=override, template_item=job.template,
						 suppress_push=True)
	counts["records_removed"] = _drop_other_records(job, kept)
	frappe.db.commit()
	log("legacy images: {0} row(s) kept, {1} pointed at a new variant, {2} left unmapped".format(
		counts["images"], counts["mapped"], counts["unmapped"]))
	return {**counts, "notes": notes}
