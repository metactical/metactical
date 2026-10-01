# Copyright (c) 2026, International Camouflage Ltd
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt

# shared header fields a batch stamps onto each of its page revisions
HEADER_FIELDS = (
	"supplier", "supplier_name", "buying_price_list", "source", "purchase_order",
	"supplier_order_confirmation", "whole_order", "use_suggested", "company",
	"company_currency", "supplier_currency", "conversion_rate", "rate_source",
	"rounding_rule", "effective_from",
)


class PriceRevisionBatch(Document):
	def pages(self):
		"""The batch's page revisions, in order."""
		return frappe.get_all(
			"Price Revision",
			filters={"batch": self.name},
			fields=["name", "page_no", "status", "docstatus", "total_items",
			        "total_price_changes", "lines_needing_review", "avg_cost_change_pct",
			        "avg_margin_before", "avg_margin_after"],
			order_by="page_no asc",
		)

	def roll_up(self, pages=None):
		"""Totals across the pages, and the batch's status derived from theirs.

		The margin/cost averages are weighted by each page's item count, so the
		batch figure matches what a single revision of all the items would show.
		"""
		pages = pages if pages is not None else self.pages()
		self.page_count = len(pages)
		self.total_items = sum(cint(p.total_items) for p in pages)
		self.total_price_changes = sum(cint(p.total_price_changes) for p in pages)
		self.lines_needing_review = sum(cint(p.lines_needing_review) for p in pages)

		def weighted(field):
			num = sum(flt(p.get(field)) * cint(p.total_items) for p in pages)
			den = sum(cint(p.total_items) for p in pages)
			return num / den if den else 0

		self.avg_cost_change_pct = weighted("avg_cost_change_pct")
		self.avg_margin_before = weighted("avg_margin_before")
		self.avg_margin_after = weighted("avg_margin_after")
		self.status = self._status_from(pages)

	def _status_from(self, pages):
		statuses = {p.status for p in pages}
		if not statuses or statuses == {"Draft"}:
			return "Draft"
		if statuses == {"Cancelled"}:
			return "Cancelled"
		if statuses == {"Reverted"}:
			return "Reverted"
		if statuses == {"Applied"}:
			return "Applied"
		if statuses <= {"Draft", "Pending Review"}:
			return "Pending Review"
		# a mix — some pages applied/reverted, others not
		return "Partially Applied"

	def save_roll_up(self):
		"""Refresh the totals and persist just those fields (pages change often;
		the batch header does not)."""
		self.roll_up()
		frappe.db.set_value("Price Revision Batch", self.name, {
			"page_count": self.page_count,
			"total_items": self.total_items,
			"total_price_changes": self.total_price_changes,
			"lines_needing_review": self.lines_needing_review,
			"avg_cost_change_pct": self.avg_cost_change_pct,
			"avg_margin_before": self.avg_margin_before,
			"avg_margin_after": self.avg_margin_after,
			"status": self.status,
		}, update_modified=True)

	def on_trash(self):
		names = frappe.get_all("Price Revision", filters={"batch": self.name}, pluck="name")
		if names:
			frappe.throw(_("{0} still has {1} page revision(s). Delete or detach them first.")
			             .format(self.name, len(names)))
