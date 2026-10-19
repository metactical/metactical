# Copyright (c) 2026, Storebuilder Commerce Inc and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ProcurementSettingsV3(Document):
	def validate(self):
		# Stored the way po_email_signature compares them: lowercase, no "@" --
		# so "@Metactical.com " and "metactical.com" are the same domain.
		seen = set()
		for row in self.get("email_signatures"):
			row.domain = (row.domain or "").strip().lstrip("@").lower()
			if row.domain in seen:
				frappe.throw(f"Row {row.idx}: domain <b>{row.domain}</b> already has a signature.")
			seen.add(row.domain)
