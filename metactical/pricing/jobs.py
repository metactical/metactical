# Copyright (c) 2026, International Camouflage Ltd
"""Background jobs for large price revisions.

A revision past ICL Pricing Settings' threshold is never built, recalculated,
applied or reverted inside a web request. The work goes to the long queue,
writes in batches with a commit and a pause after each (the way an import
does), and reports progress to the grid in real time.

One job per revision at a time: the grid is read-only while it runs and every
mutating endpoint refuses. Apply and revert are resumable: a batch that has
been written is skipped when the job runs again.
"""

from __future__ import annotations

import time

import frappe
from frappe import _
from frappe.utils import cint

EVENT = "price_revision_job"
ACTIVE = ("Queued", "Running")


def limits():
	s = frappe.get_cached_doc("ICL Pricing Settings")
	pause = s.get("batch_pause_ms")
	return {
		"threshold": cint(s.get("background_threshold")) or 300,
		"batch": cint(s.get("batch_size")) or 250,
		"pause": (250 if pause is None else cint(pause)) / 1000.0,
	}


def is_large(item_count):
	return cint(item_count) > limits()["threshold"]


def apply_threshold():
	"""Apply runs in the background when it would write more than this many
	prices/costs, so a big push to the price lists never blocks the request.
	Tunable via ICL Pricing Settings; defaults to 50."""
	s = frappe.get_cached_doc("ICL Pricing Settings")
	return cint(s.get("apply_background_threshold")) or 50


def is_busy(name):
	return frappe.db.get_value("Price Revision", name, "job_status") in ACTIVE


def ensure_idle(name):
	if is_busy(name):
		frappe.throw(_("{0} is still working in the background. Wait for it to finish.").format(name))


def start(name, operation, **kwargs):
	"""Queue ``operation`` for revision ``name``. Returns immediately."""
	if operation not in OPERATIONS:
		frappe.throw(_("Unknown operation {0}").format(operation))
	ensure_idle(name)
	frappe.db.set_value("Price Revision", name, {
		"job_status": "Queued", "job_operation": operation, "job_progress": 0,
		"job_message": _("Waiting for a worker…"),
	}, update_modified=False)
	frappe.db.commit()
	frappe.enqueue(
		"metactical.pricing.jobs.run",
		queue="long",
		timeout=4 * 3600,
		job_id="price_revision:{0}".format(name),
		deduplicate=True,
		name=name,
		operation=operation,
		user=frappe.session.user,
		kwargs=kwargs,
	)
	_publish(name, "Queued", 0, _("Waiting for a worker…"), operation)


def run(name, operation, user=None, kwargs=None):
	"""Worker entry point."""
	frappe.set_user(user or "Administrator")
	progress = Progress(name, operation, user)
	progress.update(0, 1, _("Starting…"), status="Running")
	try:
		OPERATIONS[operation](name, progress, **(kwargs or {}))
		frappe.db.commit()
		progress.finish()
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title="Price Revision job failed: {0} {1}".format(operation, name))
		msg = str(frappe.local.message_log[-1]) if frappe.local.message_log else frappe.get_traceback().strip().splitlines()[-1]
		progress.fail(msg[:500])


class Progress:
	"""Writes progress to the revision and pushes it to the user's screen."""

	DOCTYPE = "Price Revision"

	def __init__(self, name, operation, user):
		self.name, self.operation, self.user = name, operation, user
		self._last = 0.0

	def update(self, done, total, message, status="Running", force=False):
		pct = round(100.0 * done / total, 1) if total else 0
		now = time.time()
		# the database write is throttled; the screen still gets every step
		if force or now - self._last > 1.0:
			frappe.db.set_value(self.DOCTYPE, self.name, {
				"job_status": status, "job_progress": pct, "job_message": message,
			}, update_modified=False)
			frappe.db.commit()
			self._last = now
		_publish(self.name, status, pct, message, self.operation, self.user)

	def finish(self):
		frappe.db.set_value(self.DOCTYPE, self.name, {
			"job_status": "", "job_progress": 100, "job_message": _("Done"),
		}, update_modified=False)
		frappe.db.commit()
		_publish(self.name, "Done", 100, _("Done"), self.operation, self.user)

	def fail(self, message):
		frappe.db.set_value(self.DOCTYPE, self.name, {
			"job_status": "Failed", "job_message": message,
		}, update_modified=False)
		frappe.db.commit()
		_publish(self.name, "Failed", None, message, self.operation, self.user)


class BatchProgress(Progress):
	"""Same, for a whole batch (the grid listens on the same channel)."""

	DOCTYPE = "Price Revision Batch"


def _publish(name, status, pct, message, operation, user=None):
	frappe.publish_realtime(
		EVENT,
		{"name": name, "status": status, "progress": pct, "message": message, "operation": operation},
		user=user or frappe.session.user,
		after_commit=False,
	)


def pause():
	gap = limits()["pause"]
	if gap:
		time.sleep(gap)


# --------------------------------------------------------------- operations


def _edit(name, progress, change, **kw):
	"""Load the revision, apply a grid change, and save (recalculating)."""
	from metactical.pricing import api

	progress.update(1, 3, _("Loading the revision…"))
	doc = frappe.get_doc("Price Revision", name)
	progress.update(2, 3, _("Working out prices…"))
	if change == "edits":
		# a cell edit only moves the items it touched, even on a big revision
		affected = {c.get("item_code") for c in (kw.get("cells") or [])}
		affected |= {i.get("item_code") for i in (kw.get("items") or [])}
		api.CHANGES[change](doc, **kw)
		doc.save_item_edits(affected)
	else:
		api.CHANGES[change](doc, **kw)
		doc.save()


def _build(name, progress, codes, costs_list, duty_field=None):
	"""Fill a new revision built from a selection, in batches."""
	doc = frappe.get_doc("Price Revision", name)
	step = limits()["batch"] * 4
	total = len(codes)
	for i in range(0, total, step):
		part = codes[i:i + step]
		cost = dict(frappe.get_all(
			"Item Price", filters={"price_list": costs_list, "item_code": ("in", part)},
			fields=["item_code", "price_list_rate"], as_list=True,
		))
		duty = dict(frappe.get_all(
			"Item", filters={"name": ("in", part)}, fields=["name", duty_field], as_list=True,
		)) if duty_field else {}
		for code in part:
			c = cost.get(code) or 0
			doc.append("items", {
				"item_code": code, "old_cost": c, "new_cost": c,
				"duty_pct": duty.get(code) or 0, "supplier_currency": doc.supplier_currency, "apply": 1,
			})
		progress.update(min(i + step, total), total * 1.25, _("Loading items {0} of {1}").format(min(i + step, total), total))
	progress.update(total, total * 1.25, _("Working out prices for {0} items…").format(total))
	doc.save()


def _apply(name, progress):
	from metactical.icl_pricing.doctype.price_revision.price_revision import apply_revision

	doc = frappe.get_doc("Price Revision", name)
	if doc.docstatus == 0:
		progress.update(0, 1, _("Submitting…"))
		doc.submit()
		frappe.db.commit()
	apply_revision(name, progress=progress)


def _revert(name, progress):
	from metactical.icl_pricing.doctype.price_revision.price_revision import revert_revision

	revert_revision(name, progress=progress)


OPERATIONS = {
	"edit": _edit,
	"build": _build,
	"apply": _apply,
	"revert": _revert,
}


# ----------------------------------------------------------------- batches
#
# Applying or reverting a batch walks its pages, running the same per-page
# apply/revert (each ≤ a page of items, so quick). One job per batch; it
# reports progress on the batch and reloads every open page when it finishes.


def batch_is_busy(batch):
	return frappe.db.get_value("Price Revision Batch", batch, "job_status") in ACTIVE


def batch_ensure_idle(batch):
	if batch_is_busy(batch):
		frappe.throw(_("{0} is still working in the background. Wait for it to finish.").format(batch))


def start_batch(batch, operation, **kwargs):
	"""Queue a whole-batch ``operation`` (apply/revert/add_list/drop_list).
	Returns immediately."""
	if operation not in BATCH_OPERATIONS:
		frappe.throw(_("Unknown operation {0}").format(operation))
	batch_ensure_idle(batch)
	frappe.db.set_value("Price Revision Batch", batch, {
		"job_status": "Queued", "job_operation": operation, "job_progress": 0,
		"job_message": _("Waiting for a worker…"),
	}, update_modified=False)
	frappe.db.commit()
	frappe.enqueue(
		"metactical.pricing.jobs.run_batch",
		queue="long",
		timeout=8 * 3600,
		job_id="price_revision_batch:{0}".format(batch),
		deduplicate=True,
		batch=batch,
		operation=operation,
		user=frappe.session.user,
		kwargs=kwargs,
	)
	_publish(batch, "Queued", 0, _("Waiting for a worker…"), operation)


def run_batch(batch, operation, user=None, kwargs=None):
	"""Worker entry point for a batch."""
	frappe.set_user(user or "Administrator")
	progress = BatchProgress(batch, operation, user)
	progress.update(0, 1, _("Starting…"), status="Running")
	try:
		BATCH_OPERATIONS[operation](batch, progress, **(kwargs or {}))
		frappe.db.commit()
		progress.finish()
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title="Price Revision Batch job failed: {0} {1}".format(operation, batch))
		msg = str(frappe.local.message_log[-1]) if frappe.local.message_log else frappe.get_traceback().strip().splitlines()[-1]
		progress.fail(msg[:500])


def _pages(batch):
	return frappe.get_all(
		"Price Revision",
		filters={"batch": batch, "docstatus": ("<", 2)},
		fields=["name", "page_no", "status", "docstatus"],
		order_by="page_no asc",
	)


def _refresh_batch(batch):
	frappe.get_doc("Price Revision Batch", batch).save_roll_up()


def _apply_batch(batch, progress):
	from metactical.icl_pricing.doctype.price_revision.price_revision import apply_revision

	pages = _pages(batch)
	total = len(pages)
	for i, p in enumerate(pages, 1):
		progress.update(i, total, _("Applying page {0} of {1}…").format(i, total), force=True)
		if p.status == "Applied":
			continue  # resumable: a page already written is skipped
		doc = frappe.get_doc("Price Revision", p.name)
		if doc.docstatus == 0:
			doc.submit()
			frappe.db.commit()
		apply_revision(p.name)
		frappe.db.commit()
		pause()
	_refresh_batch(batch)


def _revert_batch(batch, progress):
	from metactical.icl_pricing.doctype.price_revision.price_revision import revert_revision

	pages = _pages(batch)
	total = len(pages)
	for i, p in enumerate(pages, 1):
		progress.update(i, total, _("Reverting page {0} of {1}…").format(i, total), force=True)
		if p.status != "Applied":
			continue
		revert_revision(p.name)
		frappe.db.commit()
		pause()
	_refresh_batch(batch)


def _columns_batch(batch, progress, change, price_list):
	"""Add or drop a price-list column across every page of a batch, so the
	collective keeps one shared set of columns. The batch's own column set is
	updated too, so pages made later inherit it."""
	from metactical.pricing import api

	bdoc = frappe.get_doc("Price Revision Batch", batch)
	api.CHANGES[change](bdoc, price_list=price_list)
	bdoc.save()
	frappe.db.commit()

	pages = _pages(batch)
	total = len(pages)
	for i, p in enumerate(pages, 1):
		progress.update(i, total, _("Updating page {0} of {1}…").format(i, total), force=True)
		if p.docstatus != 0:
			continue  # only draft pages can change their columns
		doc = frappe.get_doc("Price Revision", p.name)
		api.CHANGES[change](doc, price_list=price_list)
		doc.save()
		frappe.db.commit()
		pause()
	_refresh_batch(batch)


def _add_list_batch(batch, progress, price_list=None):
	_columns_batch(batch, progress, "add_list", price_list)


def _drop_list_batch(batch, progress, price_list=None):
	_columns_batch(batch, progress, "drop_list", price_list)


BATCH_OPERATIONS = {
	"apply": _apply_batch,
	"revert": _revert_batch,
	"add_list": _add_list_batch,
	"drop_list": _drop_list_batch,
}
