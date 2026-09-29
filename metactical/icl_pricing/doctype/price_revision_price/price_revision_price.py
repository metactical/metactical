# Copyright (c) 2026, International Camouflage Ltd
# For license information, please see license.txt

from frappe.model.document import Document


class PriceRevisionPrice(Document):
	def db_insert(self, *args, **kwargs):
		# the parent Price Revision writes its price rows in bulk
		if self.flags.get("saved_in_bulk"):
			return
		super().db_insert(*args, **kwargs)
