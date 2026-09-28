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

	def __init__(self, name, operation, user):
		self.name, self.operation, self.user = name, operation, user
		self._last = 0.0

	def update(self, done, total, message, status="Running", force=False):
		pct = round(100.0 * done / total, 1) if total else 0
		now = time.time()
		# the database write is throttled; the screen still gets every step
		if force or now - self._last > 1.0:
			frappe.db.set_value("Price Revision", self.name, {
				"job_status": status, "job_progress": pct, "job_message": message,
			}, update_modified=False)
			frappe.db.commit()
			self._last = now
		_publish(self.name, status, pct, message, self.operation, self.user)

	def finish(self):
		frappe.db.set_value("Price Revision", self.name, {
			"job_status": "", "job_progress": 100, "job_message": _("Done"),
		}, update_modified=False)
		frappe.db.commit()
		_publish(self.name, "Done", 100, _("Done"), self.operation, self.user)

	def fail(self, message):
		frappe.db.set_value("Price Revision", self.name, {
			"job_status": "Failed", "job_message": message,
		}, update_modified=False)
		frappe.db.commit()
		_publish(self.name, "Failed", None, message, self.operation, self.user)


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
