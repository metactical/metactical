# Copyright (c) 2026, Storebuilder Commerce Inc and contributors
# For license information, please see license.txt
"""One row per provider call: what was asked, what came back, what it cost.

Request and response are kept together on purpose - a reply only means something next to the
question, and chasing the pair across two records is how nobody ever reads either.
"""
import frappe
from frappe.model.document import Document
from frappe.utils import add_days, cint, now_datetime


class AIRequestLog(Document):
	pass


def clear_old_logs():
	"""Daily. Keeps the log from growing without bound, at the age set on AI Settings."""
	days = cint(frappe.db.get_single_value("AI Settings", "log_retention_days"))
	if days <= 0:
		return
	frappe.db.delete("AI Request Log", {"creation": ["<", add_days(now_datetime(), -days)]})
	frappe.db.commit()
