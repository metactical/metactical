# Copyright (c) 2026, Storebuilder Commerce Inc and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import cint


class S3ProductImageMetaData(Document):
	pass


def upsert_upload(entries, override_full_product=0):
	"""Create ONE submitted record for an upload from its per-SKU entries.

	`entries` is the atomic per-SKU view:
	    [{ "sku", "item_code", "sites": [...], "images": [{order,icon,small,medium,large}] }]
	Each SKU's sites and images are stored tagged with that SKU (`nat_sku`), so the
	products can be re-merged when building the JSON back out.
	"""
	entries = [e for e in entries if e.get("sku")]
	if not entries:
		return None

	doc = frappe.new_doc("S3 Product Image Meta Data")
	doc.nat_override_full_product = 1 if cint(override_full_product) else 0
	doc.nat_uploaded_by = frappe.session.user

	for entry in entries:
		sku = entry["sku"]
		doc.append("nat_skus", {"nat_item_code": entry.get("item_code"), "nat_sku": sku})

		for site in entry.get("sites") or []:
			doc.append("nat_sites", {"nat_site": site, "nat_sku": sku})

		for image in entry.get("images") or []:
			doc.append(
				"nat_images",
				{
					"nat_sku": sku,
					"nat_image_order": image.get("order") or 0,
					"nat_icon": image.get("icon"),
					"nat_small": image.get("small"),
					"nat_medium": image.get("medium"),
					"nat_large": image.get("large"),
				},
			)

	doc.insert(ignore_permissions=True)
	doc.submit()
	return doc.name
