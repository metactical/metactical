# Copyright (c) 2024, Techlift Technologies and contributors
# For license information, please see license.txt

import mimetypes
import re

import frappe
from frappe.model.document import Document

class WebsiteSpecificationLabel(Document):
	def validate(self):
		for row in self.descriptions:
			row.description = row.description.strip()
		self.upload_swash_images()

	def on_update(self):
		# The local copies go only once the S3 URLs are saved on the rows
		for name in self.flags.get("uploaded_swash_files") or []:
			frappe.delete_doc("File", name, ignore_permissions=True)

	def upload_swash_images(self):
		"""Move newly attached swash images to the swash image bucket in S3 Settings.

		An image attached in the grid is a local file until the label is saved;
		the row then keeps the S3 URL instead.
		"""
		rows = [row for row in self.descriptions
			if (row.nat_swash_image or "").startswith(("/files/", "/private/files/"))]
		if not rows:
			return

		settings = frappe.get_single("S3 Settings")
		self.flags.uploaded_swash_files = []
		for row in rows:
			file = frappe.get_doc("File", {"file_url": row.nat_swash_image})
			# The content hash keeps two different images with the same file name apart;
			# anything but letters, digits, dots and dashes would need escaping in the URL
			key = "{0}/{1}-{2}".format(frappe.scrub(self.name),
				(file.content_hash or frappe.generate_hash(length=10))[:10],
				re.sub(r"[^\w.\-]+", "-", file.file_name))
			row.nat_swash_image = settings.upload_swash_image(key, file.get_content(),
				mimetypes.guess_type(file.file_name)[0])
			self.flags.uploaded_swash_files.append(file.name)
