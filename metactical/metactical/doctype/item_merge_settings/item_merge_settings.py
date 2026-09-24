# Copyright (c) 2026, Storebuilder Commerce Inc and contributors
# For license information, please see license.txt
"""What a merge copies between items, and which websites Item Merge may read from Storebuilder."""
import frappe
from frappe.model.document import Document

DEFAULT_TIMEOUT = 120


class NotConfigured(Exception):
	"""Metabase is off, or missing its URL, key or a database id - the caller reports it and stops."""


class ItemMergeSettings(Document):
	def validate(self):
		seen = set()
		for row in self.storebuilder_websites or []:
			if row.price_list in seen:
				frappe.throw("{0} is listed more than once under Storebuilder Websites".format(
					row.price_list))
			seen.add(row.price_list)


def get_settings():
	return frappe.get_cached_doc("Item Merge Settings")
