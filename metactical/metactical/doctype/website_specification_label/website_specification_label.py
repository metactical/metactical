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
		self.upload_swatch_images()

	def on_update(self):
		# The local copies go only once the S3 URLs are saved on the rows
		for name in self.flags.get("uploaded_swatch_files") or []:
			frappe.delete_doc("File", name, ignore_permissions=True)

	def upload_swatch_images(self):
		"""Move newly attached swatch images to the swatch image bucket in S3 Settings.

		An image attached in the grid is a local file until the label is saved;
		the row then keeps the S3 URL instead.
		"""
		rows = [row for row in self.descriptions
			if (row.nat_swatch_image or "").startswith(("/files/", "/private/files/"))]
		if not rows:
			return

		settings = frappe.get_single("S3 Settings")
		self.flags.uploaded_swatch_files = []
		for row in rows:
			file = frappe.get_doc("File", {"file_url": row.nat_swatch_image})
			# The content hash keeps two different images with the same file name apart;
			# anything but letters, digits, dots and dashes would need escaping in the URL
			# The folder is the label as a slug: "Items - Filter - Colour" -> items-filter-colour
			key = "{0}/{1}-{2}".format(re.sub(r"[^a-z0-9]+", "-", self.name.lower()).strip("-"),
				(file.content_hash or frappe.generate_hash(length=10))[:10],
				re.sub(r"[^\w.\-]+", "-", file.file_name))
			row.nat_swatch_image = settings.upload_swatch_image(key, file.get_content(),
				mimetypes.guess_type(file.file_name)[0])
			self.flags.uploaded_swatch_files.append(file.name)
