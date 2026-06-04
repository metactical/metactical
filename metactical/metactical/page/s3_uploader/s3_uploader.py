import base64
import json

import frappe

from metactical.metactical.doctype.s3_product_image_meta_data.s3_product_image_meta_data import (
	upsert_upload,
)
from metactical.metactical.doctype.s3_settings.s3_settings import BASE_PREFIX


def _get_settings():
	return frappe.get_single("S3 Settings")


@frappe.whitelist()
def get_public_config():
	"""Non-secret S3 config for the frontend (never returns the secret key)."""
	return _get_settings().get_public_config()


@frappe.whitelist()
def get_sites():
	"""Selectable sites: Lead Sources that have a Lead Source Domain set."""
	return frappe.get_all(
		"Lead Source",
		filters={"lead_source_domain": ["!=", ""]},
		fields=["name"],
		order_by="name",
	)


@frappe.whitelist()
def get_item_sku(item_code):
	"""Resolve an Item Code to its retail SKU (ifw_retailskusuffix).

	Returns {item_code, sku, error}. `sku` is None when the item is missing or
	has no RetailSKUSuffix so the frontend can flag it.
	"""
	
	item = frappe.get_doc("Item", item_code)
	
	if not item:
		return {"item_code": item_code, "sku": None, "error": "Item not found"}

	sku = item.ifw_retailskusuffix
	if not sku:
		return {"item_code": item_code, "sku": None, "error": "Item has no RetailSKUSuffix"}

	return {"item_code": item_code, "sku": sku}


@frappe.whitelist()
def test_connection():
	"""Backend verification of the S3 credentials against the configured bucket."""
	settings = _get_settings()
	try:
		client = settings.get_client(ignore_disabled=True)
		client.list_objects_v2(Bucket=settings.nat_bucket_name, MaxKeys=1)
		return {"success": True, "message": "Connection successful. S3 credentials verified."}
	except frappe.ValidationError:
		raise
	except Exception as e:
		return {"success": False, "message": _friendly_s3_error(e, settings.nat_bucket_name, settings.nat_region)}


@frappe.whitelist()
def upload_image(filename, role, content, content_type=None):
	"""Upload a single image to S3, then HEAD-verify it landed.

	`content` is the base64-encoded file (optionally a data URL). Returns the S3
	key, public URL, and a `verified` flag from the post-upload HEAD check.
	"""
	settings = _get_settings()
	client = settings.get_client()

	key = f"{BASE_PREFIX}/{role}/{filename}"
	body = base64.b64decode(_strip_data_url(content))

	put_args = {"Bucket": settings.nat_bucket_name, "Key": key, "Body": body}
	if content_type:
		put_args["ContentType"] = content_type

	try:
		client.put_object(**put_args)
	except Exception as e:
		# Surface a clean message to the uploader instead of a raw traceback.
		frappe.throw(_friendly_s3_error(e, settings.nat_bucket_name, settings.nat_region))

	verified = False
	try:
		client.head_object(Bucket=settings.nat_bucket_name, Key=key)
		verified = True
	except Exception:
		verified = False

	return {
		"success": True,
		"key": key,
		"full_url": f"{settings.public_url_base}/{key}",
		"verified": verified,
	}


@frappe.whitelist()
def save_metadata(entries, override_full_product=0):
	"""Store one upload as a single S3 Product Image Meta Data record.

	`entries` is the per-SKU array produced by the uploader; sites/images are stored
	tagged with their SKU.
	"""
	if isinstance(entries, str):
		entries = json.loads(entries)

	name = upsert_upload(entries, override_full_product)
	frappe.db.commit()
	return {"success": True, "records": [name] if name else []}


@frappe.whitelist()
def list_metadata(filter=None):
	"""List submitted S3 Product Image Meta Data records (optionally by SKU)."""
	record_filters = {"docstatus": 1}
	if filter:
		# SKUs live on the child table now; find parents with a matching SKU.
		parents = frappe.get_all(
			"S3 Product Image SKU",
			filters={"nat_sku": ["like", f"%{filter}%"]},
			pluck="parent",
		)
		if not parents:
			return []
		record_filters["name"] = ["in", list(set(parents))]

	records = frappe.get_all(
		"S3 Product Image Meta Data",
		filters=record_filters,
		fields=["name", "modified"],
		order_by="modified desc",
	)

	for record in records:
		skus = frappe.get_all(
			"S3 Product Image SKU",
			filters={"parent": record["name"]},
			pluck="nat_sku",
		)
		record["skus"] = skus
		# Display label for the modal (first SKU, or the record name as a fallback).
		record["product_sku"] = skus[0] if skus else record["name"]

	return records


@frappe.whitelist()
def get_metadata(name):
	"""Return one S3 Product Image Meta Data record shaped like the uploader metadata."""
	doc = frappe.get_doc("S3 Product Image Meta Data", name)

	return {
		"productsku": [row.nat_sku for row in doc.nat_skus],
		"skuItems": [{"item_code": row.nat_item_code, "sku": row.nat_sku} for row in doc.nat_skus],
		"sites": [row.nat_site for row in doc.nat_sites],
		"overrideFullProduct": bool(doc.nat_override_full_product),
		"images": [
			{
				"order": row.nat_image_order,
				"icon": row.nat_icon,
				"small": row.nat_small,
				"medium": row.nat_medium,
				"large": row.nat_large,
			}
			for row in doc.nat_images
		],
	}


@frappe.whitelist()
def build_export_json(names=None):
	"""Rebuild the export JSON ({"products": [...]}) from stored metadata records.

	Each record holds one upload, stored per-SKU. SKUs whose sites AND images are
	identical are merged into one product (productsku lists all of them). Pass `names`
	(a JSON list or single name) to limit records; otherwise all submitted records.
	"""
	if isinstance(names, str):
		names = json.loads(names) if names.strip().startswith("[") else [names]

	filters = {"docstatus": 1}
	if names:
		filters["name"] = ["in", names]

	record_names = frappe.get_all(
		"S3 Product Image Meta Data", filters=filters, order_by="creation asc", pluck="name"
	)

	products = []
	for name in record_names:
		doc = frappe.get_doc("S3 Product Image Meta Data", name)

		# Group sites/images by their SKU tag.
		sites_by_sku = {}
		for row in doc.nat_sites:
			sites_by_sku.setdefault(row.nat_sku, []).append(row.nat_site)

		images_by_sku = {}
		for row in doc.nat_images:
			images_by_sku.setdefault(row.nat_sku, []).append(
				{
					"order": row.nat_image_order or 0,
					"icon": row.nat_icon,
					"small": row.nat_small,
					"medium": row.nat_medium,
					"large": row.nat_large,
				}
			)

		override = bool(doc.nat_override_full_product)

		# Build a product per SKU, then merge SKUs with identical sites + images.
		by_sig = {}
		seen = set()
		for sku_row in doc.nat_skus:
			sku = sku_row.nat_sku
			if not sku or sku in seen:
				continue
			seen.add(sku)

			sites = sites_by_sku.get(sku, [])
			images = sorted(images_by_sku.get(sku, []), key=lambda i: i["order"])
			sig = json.dumps({"sites": sorted(sites), "images": images}, sort_keys=True)

			if sig not in by_sig:
				by_sig[sig] = {
					"productsku": [sku],
					"sites": sites,
					"overrideFullProduct": override,
					"images": images,
				}
				products.append(by_sig[sig])
			else:
				by_sig[sig]["productsku"].append(sku)

	return {"products": products}


def _strip_data_url(content):
	"""Accept either a bare base64 string or a `data:<type>;base64,<data>` URL."""
	if content and content.startswith("data:") and "," in content:
		return content.split(",", 1)[1]
	return content


def _friendly_s3_error(error, bucket, region):
	message = str(error)
	if "403" in message or "AccessDenied" in message or "Forbidden" in message:
		return f"Access forbidden. Verify your IAM permissions for the {bucket} bucket."
	if "404" in message or "NoSuchBucket" in message or "Not Found" in message:
		return f"Bucket not found. Verify the {bucket} bucket exists in {region}."
	if "InvalidAccessKeyId" in message or "SignatureDoesNotMatch" in message:
		return "Invalid AWS credentials. Check the access key and secret."
	return f"Connection failed: {message}"
