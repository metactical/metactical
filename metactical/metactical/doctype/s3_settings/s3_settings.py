# Copyright (c) 2026, Storebuilder Commerce Inc and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

# Root key prefix under which product images are stored in the bucket.
BASE_PREFIX = "images/products"


class S3Settings(Document):
	def get_client(self, ignore_disabled=False):
		"""Build a boto3 S3 client from the stored credentials.

		Raises a clear error if the uploader is disabled or not fully configured.
		Pass ``ignore_disabled=True`` for read-only actions like the connection
		test, which should work even while the uploader is disabled.
		"""
		if self.disabled and not ignore_disabled:
			frappe.throw("S3 Uploader is disabled. Enable it in S3 Settings.")

		if not (self.bucket_name and self.region and self.aws_access_key_id):
			frappe.throw("S3 Settings are incomplete. Set bucket, region and credentials.")

		import boto3

		secret = self.get_password("aws_secret_access_key", raise_exception=False)
		if not secret:
			frappe.throw("S3 Settings are missing the AWS secret access key.")

		return boto3.client(
			"s3",
			region_name=self.region,
			aws_access_key_id=self.aws_access_key_id,
			aws_secret_access_key=secret,
		)

	@property
	def public_url_base(self):
		"""Derive the public bucket URL base from bucket + region."""
		if not (self.bucket_name and self.region):
			return ""
		return f"https://{self.bucket_name}.s3.{self.region}.amazonaws.com"

	def get_public_config(self):
		"""Return only non-secret config for the frontend (never the secret key)."""
		return {
			"disabled": bool(self.disabled),
			"bucket_name": self.bucket_name,
			"region": self.region,
			"base_prefix": BASE_PREFIX,
			"public_url_base": self.public_url_base,
		}
