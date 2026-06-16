# Copyright (c) 2026, Storebuilder Commerce Inc and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.model.naming import append_number_if_name_exists
from frappe.utils import cint, now_datetime


class S3ProductImageMetaData(Document):
	pass


def _build_record_name(template_item):
	"""Readable record name: "<template item code> <timestamp>".

	e.g. "UMX225245-01 jun 16 2026 8:09:12". A numeric suffix is appended if a
	record with the same name already exists (two uploads in the same second).
	"""
	dt = now_datetime()
	stamp = f"{dt.strftime('%b')} {dt.day} {dt.year} {dt.hour}:{dt.minute:02d}:{dt.second:02d}"
	base = f"{template_item} {stamp}" if template_item else stamp
	return append_number_if_name_exists("S3 Product Image Meta Data", base)
	

def upsert_upload(files, override_full_product=0, template_item=None):
	"""Create ONE submitted record for an upload from its per-FILE records.

	`files` is one entry per uploaded image::

	    [{ "role", "order", "path", "skuItems": [{item_code, sku}], "sites": [...] }]

	SKUs go to `nat_skus`; images are grouped by (sku, order) into `nat_images`
	(role columns); and each site is stored tagged with its image's SKU + order +
	role on `nat_sites`, so sites can be restored per image (not unioned).

	The record is named "<template_item> <timestamp>" for readability.
	"""
	files = [f for f in files if f.get("role") and (f.get("skuItems") or [])]
	if not files:
		return None

	doc = frappe.new_doc("S3 Product Image Meta Data")
	doc.nat_override_full_product = 1 if cint(override_full_product) else 0
	doc.nat_uploaded_by = frappe.session.user

	# Give the record a human-readable name instead of a random hash.
	doc.name = _build_record_name(template_item)
	doc.flags.name_set = True

	seen_skus = {}
	image_rows = {}  # (sku, order) -> nat_images row

	for f in files:
		role = f["role"]
		order = f.get("order") or 0
		path = f.get("path")
		sites = f.get("sites") or []

		for item in f["skuItems"]:
			sku = item.get("sku")
			if not sku:
				continue

			if sku not in seen_skus:
				seen_skus[sku] = True
				doc.append("nat_skus", {"nat_item_code": item.get("item_code"), "nat_sku": sku})

			row = image_rows.get((sku, order))
			if not row:
				row = doc.append("nat_images", {"nat_sku": sku, "nat_image_order": order})
				image_rows[(sku, order)] = row
			row.set("nat_" + role, path)

			for site in sites:
				doc.append(
					"nat_sites",
					{"nat_site": site, "nat_sku": sku, "nat_image_order": order, "nat_role": role},
				)

	doc.insert(ignore_permissions=True)
	doc.submit()
	return doc.name
