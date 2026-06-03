import base64
import json

import frappe

from metactical.metactical.doctype.s3_product_image_meta_data.s3_product_image_meta_data import (
	upsert_from_metadata,
)
from metactical.metactical.doctype.s3_settings.s3_settings import BASE_PREFIX


def _get_settings():
	return frappe.get_single("S3 Settings")


@frappe.whitelist()
def get_public_config():
	"""Non-secret S3 config for the frontend (never returns the secret key)."""
	return _get_settings().get_public_config()


@frappe.whitelist()
def test_connection():
	"""Backend verification of the S3 credentials against the configured bucket."""
	settings = _get_settings()
	try:
		client = settings.get_client(ignore_disabled=True)
		client.list_objects_v2(Bucket=settings.bucket_name, MaxKeys=1)
		return {"success": True, "message": "Connection successful. S3 credentials verified."}
	except frappe.ValidationError:
		raise
	except Exception as e:
		return {"success": False, "message": _friendly_s3_error(e, settings.bucket_name, settings.region)}


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

	put_args = {"Bucket": settings.bucket_name, "Key": key, "Body": body}
	if content_type:
		put_args["ContentType"] = content_type

	try:
		client.put_object(**put_args)
	except Exception as e:
		# Surface a clean message to the uploader instead of a raw traceback.
		frappe.throw(_friendly_s3_error(e, settings.bucket_name, settings.region))

	verified = False
	try:
		client.head_object(Bucket=settings.bucket_name, Key=key)
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
def save_metadata(products):
	"""Store the grouped product metadata as S3 Product Image Meta Data records."""
	if isinstance(products, str):
		products = json.loads(products)

	names = []
	for product in products:
		name = upsert_from_metadata(product)
		if name:
			names.append(name)

	frappe.db.commit()
	return {"success": True, "records": names}


@frappe.whitelist()
def list_metadata(filter=None):
	"""List submitted S3 Product Image Meta Data records (optionally by SKU)."""
	filters = {"docstatus": 1}
	if filter:
		filters["product_sku"] = ["like", f"%{filter}%"]

	records = frappe.get_all(
		"S3 Product Image Meta Data",
		filters=filters,
		fields=["name", "product_sku", "modified"],
		order_by="modified desc",
	)

	for record in records:
		record["skus"] = frappe.get_all(
			"S3 Product Image SKU",
			filters={"parent": record["name"]},
			pluck="sku",
		)

	return records


@frappe.whitelist()
def get_metadata(name):
	"""Return one S3 Product Image Meta Data record shaped like the uploader metadata."""
	doc = frappe.get_doc("S3 Product Image Meta Data", name)

	return {
		"productsku": [row.sku for row in doc.skus],
		"sites": [row.site for row in doc.sites],
		"overrideFullProduct": bool(doc.override_full_product),
		"images": [
			{
				"order": row.image_order,
				"icon": row.icon,
				"small": row.small,
				"medium": row.medium,
				"large": row.large,
			}
			for row in doc.images
		],
	}


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
