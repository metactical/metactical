# Copyright (c) 2026, Storebuilder Commerce Inc and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class S3ProductImageMetaData(Document):
	pass


def upsert_from_metadata(product):
	skus = [s for s in (product.get("productsku") or []) if s]
	if not skus:
		return None

	product_sku = skus[0]

	doc = frappe.new_doc("S3 Product Image Meta Data")
	doc.nat_product_sku = product_sku
	doc.nat_override_full_product = 1 if product.get("overrideFullProduct") else 0
	doc.nat_uploaded_by = frappe.session.user

	for sku in skus:
		doc.append("nat_skus", {"nat_sku": sku})

	for site in product.get("sites") or []:
		doc.append("nat_sites", {"nat_site": site})

	for image in product.get("images") or []:
		doc.append(
			"nat_images",
			{
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
