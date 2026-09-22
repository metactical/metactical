# Copyright (c) 2026, Storebuilder Commerce Inc and contributors
# For license information, please see license.txt
"""One row per provider call: what was asked, what came back, what it cost.

Request and response are kept together on purpose - a reply only means something next to the
question, and chasing the pair across two records is how nobody ever reads either.

This is a **log doctype**: `clear_old_logs` is the interface Frappe's Log Settings looks for
(`frappe.core.doctype.log_settings.log_settings.LogType`), and `default_log_clearing_doctypes`
in hooks registers it with a default age. Nothing here needs a scheduler entry of its own.
"""
import frappe
from frappe.model.document import Document
from frappe.query_builder import Interval
from frappe.query_builder.functions import Now


class AIRequestLog(Document):
	@staticmethod
	def clear_old_logs(days=90):
		table = frappe.qb.DocType("AI Request Log")
		frappe.db.delete(table, filters=(table.modified < (Now() - Interval(days=days))))
