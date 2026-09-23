"""Item Merge Jobs: the merge itself and item-code/name/SKU changes, run in the long queue.

A job's truth lives in two places: the Item Merge Job document (what was asked, how each row went,
the log) and the items themselves (whether they exist, Item Merge History, reposts, bins). The
status call reads both, so progress survives a worker restart and anyone can reopen a job later.
Progress is pushed to the page with publish_realtime; the page also polls while a job is active.
"""
import json
import time
from contextlib import contextmanager

import frappe
from frappe.utils import now_datetime, time_diff_in_seconds

from metactical.item_merge import (family, inventory, legacy_images, legacy_products, merge,
								   product_details, rules)
from metactical.item_merge.family import exists, message_of
from metactical.item_merge.pairing import variant_attribute
from metactical.item_merge.rules import UserError

DOCTYPE = "Item Merge Job"
PROGRESS_EVENT = "item_merge_progress"
ACTIVE = ("Queued", "Running")

# No outbound Webhook may fire while a family is half restructured: on the server, Item alone
# carries three unconditional ones plus one on `doc.variant_of` - every variant save - and
# Item Price, Pricing Rule, Item Merge History and Item Group carry more. in_import is the first
# thing frappe's run_webhooks checks, so it returns before queueing anything. item_from_excel has
# to be set with it: CustomItem.validate clears in_import unless that flag is on, which would let
# every Item save through. The sites are updated once, deliberately, by the website steps at the
# end of the job. frappe.flags proxies frappe.local.flags, which is thread-local, so a concurrent
# request in this worker keeps its webhooks.
WEBHOOK_FLAGS = ("in_import", "item_from_excel")
LOG_LINES = 400

# Where run_job parks the flag values it found, so the one step that is *supposed* to reach the
# websites can put them back for as long as it needs. frappe.local is thread-local, like the flags.
SAVED_FLAGS = "_item_merge_webhook_flags"


@contextmanager
def with_webhooks():
	"""Let webhooks fire again inside a job.

	Everything in a merge runs with in_import and item_from_excel set, which is what stops frappe
	queueing a webhook for the hundreds of saves, renames and deletes a merge makes. Two things are
	the exception: the legacy drop, where reaching the websites is the whole point and a drop log
	inserted with the flags still on would sit there having quietly told nobody, and an item changes
	job, which is a set of finished edits rather than a half-finished restructuring.
	"""
	before = {name: frappe.local.flags.get(name) for name in WEBHOOK_FLAGS}
	restore = getattr(frappe.local, SAVED_FLAGS, None) or {name: None for name in WEBHOOK_FLAGS}
	for name in WEBHOOK_FLAGS:
		frappe.local.flags[name] = restore.get(name)
	try:
		yield
	finally:
		for name, value in before.items():
			frappe.local.flags[name] = value


# ---------- small helpers ----------

def _stamp():
	return now_datetime().strftime("%Y-%m-%d %H:%M:%S")


def _publish(job, line=None):
	frappe.publish_realtime(PROGRESS_EVENT, {"job": job.name, "template": job.template, "status": job.status,
											 "processed": job.processed, "total": job.total, "line": line},
							user=job.owner)


def _set(job, **values):
	"""Persist job fields straight away: the page reads them while the job is still running."""
	job.update(values)
	frappe.db.set_value(DOCTYPE, job.name, values, update_modified=False)
	frappe.db.commit()
	_publish(job)


def _set_row(row, **values):
	row.update(values)
	frappe.db.set_value(row.doctype, row.name, values, update_modified=False)
	frappe.db.commit()


class JobLog:
	"""Callable logger: appends a line to the job's log and pushes it to the page."""

	def __init__(self, job):
		self.job = job

	def __call__(self, message):
		line = f"{_stamp()} {message}"
		lines = (self.job.log or "").splitlines()[-(LOG_LINES - 1):] + [line]
		self.job.log = "\n".join(lines)
		frappe.db.set_value(DOCTYPE, self.job.name, "log", self.job.log, update_modified=False)
		frappe.db.commit()
		_publish(self.job, line)


def _steps(job):
	return json.loads(job.steps or "[]")


def _step(job, name, status, message=""):
	steps = [s for s in _steps(job) if s["name"] != name] + [{"name": name, "status": status, "message": message, "at": _stamp()}]
	_set(job, steps=json.dumps(steps))


def _job_id(name):
	return f"item-merge-{name}"


def _enqueue(job):
	# merge_job, not job_name: frappe.enqueue keeps job_name for itself and would not pass it on
	frappe.enqueue("metactical.item_merge.jobs.run_job", queue="long", timeout=max(3600, 90 * (job.total or 1)),
				   job_id=_job_id(job.name), deduplicate=True, enqueue_after_commit=True, merge_job=job.name)


def _active_job(template):
	return frappe.db.get_value(DOCTYPE, {"template": template, "status": ["in", ACTIVE]}, "name")


# ---------- merge jobs ----------

def _legacy_rows(template):
	"""The legacy Storebuilder products this merge will drop: one per template it consolidated away,
	per website.

	Read from the Legacy Website Product register by the **surviving** template, not from whatever
	the browser sent: the External IDs and slugs are captured on the Find Template screen, before
	anything is combined, and by now the templates they name are deleted - the register is all that
	outlives them. A merge with nothing registered has no legacy product to remove.

	The survivor is in there too, and stays: `_still_owned` is what decides at drop time that its
	slug is published by a live Item and leaves it alone.
	"""
	return legacy_products.for_template(template)


def create_merge_job(template, pairs, leftovers, options):
	running = _active_job(template)
	if running:
		raise UserError(f"Job {running} is already queued or running for {template} - wait for it to finish")
	check = family.check_plan(template, pairs, leftovers)
	blocking = [p for p in check["problems"] if "stock history" in p or "not a variant" in p or "more than once" in p
				or "not an old variant" in p or "Variant Number item" in p or "both merged" in p]
	blocking += rules.pair_edit_problems(pairs)
	if blocking:
		raise UserError("Fix these before queueing: " + " · ".join(blocking[:6]))
	legacy_rows = _legacy_rows(template)
	options = options or {}
	job = frappe.get_doc({
		"doctype": DOCTYPE, "job_type": "Merge", "template": template, "status": "Queued",
		"total": len(pairs), "processed": 0,
		"options": json.dumps({"sku": options.get("sku") or "keep", "fix_names": bool(options.get("fix_names", True))}),
		"steps": "[]",
		"pairs": [{"old_item": p["old"], "new_item": p["new"], "status": "Queued",
				   "item_name": str(p.get("item_name") or "").strip() or None,
				   "retail_sku": str(p.get("retail_sku") or "").strip() or None} for p in pairs],
		"leftovers": [{"item_code": c, "status": "Queued"} for c in leftovers or []],
		"legacy_products": legacy_rows,
	}).insert()
	family.add_activity(template, f"queued merge job {job.name}: {len(pairs)} pair(s), {len(leftovers or [])} leftover(s)"
								  + (f", {len(legacy_rows)} legacy website product(s) to drop" if legacy_rows else ""))
	_enqueue(job)
	return job.name


def run_job(merge_job):
	job_name = merge_job
	job = frappe.get_doc(DOCTYPE, job_name)
	if job.status not in ACTIVE:
		return
	_set(job, status="Running", started_on=job.started_on or now_datetime(), error=None)
	log = JobLog(job)
	before = {name: frappe.local.flags.get(name) for name in WEBHOOK_FLAGS}
	setattr(frappe.local, SAVED_FLAGS, before)
	for name in WEBHOOK_FLAGS:
		frappe.local.flags[name] = True
	try:
		if job.job_type == "Item Changes":
			# An item changes job is not a restructuring: it renames variants and edits their names
			# and retail SKUs, one finished edit at a time, and every one of them is something the
			# websites have to hear about. It has no website step at the end to put them back in
			# step either - unlike a merge - so held-back webhooks here would never be made up for.
			log("website webhooks left on for this job - each change is sent as it is made")
			with with_webhooks():
				run_changes(job, log)
		else:
			log("website webhooks held back for this job - the sites are updated once, at the end")
			run_merge(job, log)
	except Exception as e:  # surfaced on the job rather than lost in the worker log
		frappe.db.rollback()
		frappe.log_error(title=f"Item Merge Job {job_name}", message=frappe.get_traceback())
		log(f"ERROR {message_of(e)}")
		_set(job, status="Failed", finished_on=now_datetime(), error=message_of(e)[:1000])
	finally:
		for name, value in before.items():
			frappe.local.flags[name] = value
		setattr(frappe.local, SAVED_FLAGS, None)


def run_merge(job, log):
	opts = json.loads(job.options or "{}")
	template = job.template
	log(f"=== job {job.name}: {len(job.pairs)} pair(s), {len(job.leftovers)} leftover(s) as {frappe.session.user}")

	pending = [p for p in job.pairs if p.status not in ("Ok", "Skipped")]
	fixed = family.fix_settings(template, [{"old": p.old_item, "new": p.new_item} for p in pending if exists(p.old_item)], log=log)
	frappe.db.commit()
	_step(job, "Align settings on new variants", "done", f"{len(fixed['changed'])} item(s) adjusted")

	if not frappe.db.get_value("Item", template, "is_stock_item") and any(r["set"].get("is_stock_item") for r in fixed["changed"]):
		family.update_template(template, {"is_stock_item": 1}, log)
		frappe.db.commit()
		log(f"template {template}: is_stock_item 0 -> 1")

	failed = False
	todo = [p for p in job.pairs if p.status not in ("Ok", "Skipped")]
	for i, p in enumerate(todo):
		_set_row(p, status="Running", message=None)
		try:
			status, details = merge.merge_pair({"old": p.old_item, "new": p.new_item, "item_name": p.item_name,
												"retail_sku": p.retail_sku}, log,
											   fix_names=opts.get("fix_names", True), sku=opts.get("sku") or "keep")
		except Exception as e:  # reported on the pair, then the job stops
			frappe.db.rollback()
			frappe.log_error(title=f"Item Merge {p.old_item} -> {p.new_item}", message=frappe.get_traceback())
			status, details = "failed", {"message": message_of(e)}
			log(f"FAIL {p.old_item} -> {p.new_item}: {details['message'][:300]}")
		_set_row(p, status=status.title(), message=(details.get("message") or "")[:1000] or None,
				 **{k: details[k] for k in ("snapshot", "old_qty", "new_qty_before", "expected_qty") if k in details})
		_set(job, processed=sum(x.status in ("Ok", "Skipped") for x in job.pairs))
		if status == "failed":
			failed = True
			log("STOPPED on failure - fix the cause, then Resume; merged pairs are skipped")
			break
		if i < len(todo) - 1:
			time.sleep(merge.MERGE_SPACING_S)
	_step(job, "Merge old variants into new", "failed" if failed else "done", f"{job.processed}/{len(job.pairs)} merged")

	if not failed:
		# leftovers first: an old Variant Number variant still present keeps Variant Number on the template
		_delete_leftovers(job, log)
		_drop_variant_number(job, template, log)
		# The images come off the legacy products while they are still there to ask, and are
		# re-pointed at the new variants before anything is deleted.
		_pull_legacy_images(job, log)
		# Last, and only once the survivor's own website rows are filled: the guard in issue_drops
		# reads them to make sure a legacy slug is not the one the consolidated product now uses.
		_drop_legacy_products(job, log)
		# Stock first, so the push carries the right quantities.
		_settle_inventory(job, log)
		# Then the push, and only then the check - the drops have to land before the consolidated
		# product goes out, or a drop queued behind it would delete what was just sent.
		_push_to_websites(job, template, log)
		# The images go after the product: they hang off its variants' SKUs.
		_push_images(job, template, log)
		_verify_websites(job, template, log)

	_set(job, status="Failed" if failed else "Done", finished_on=now_datetime())
	family.add_activity(template, f"merge job {job.name} {job.status.lower()}: {job.processed}/{len(job.pairs)} merged")
	log(f"=== job {job.status.lower()}")


def _drop_variant_number(job, template, log):
	"""Drop the legacy numeric attribute this family hangs off, once nothing still uses it. Which
	attribute that is comes from the template itself, not from a constant."""
	tdoc = frappe.get_doc("Item", template).as_dict()
	legacy = variant_attribute(tdoc)
	step = f"Remove {legacy} from template"
	if not any(a.get("attribute") == legacy for a in tdoc.get("attributes") or []):
		return
	docs = family.load_items(family.variant_codes(template))
	vn_only = sorted(c for c, d in docs.items() if not family.is_new(d, legacy))
	if vn_only:
		_step(job, step, "skipped", f"{len(vn_only)} {legacy} variant(s) still under the template: {vn_only[:4]}")
		return
	family.update_template(template, {"attributes": family.template_attribute_rows(tdoc, drop=legacy)}, log)
	frappe.db.commit()
	log(f"template {template}: removed {legacy}")
	_step(job, step, "done")


def _delete_leftovers(job, log):
	if not job.leftovers:
		return
	backup, allowed = json.loads(job.deleted_pricing_rules or "[]"), {x.item_code for x in job.leftovers}
	for x in job.leftovers:
		if x.status == "Deleted":
			continue
		if not exists(x.item_code):
			_set_row(x, status="Deleted", message="already gone")
		elif merge.ledger_count(x.item_code):
			_set_row(x, status="Kept", message="has stock history")
		else:
			_set_row(x, snapshot=json.dumps(frappe.get_doc("Item", x.item_code).as_dict(), default=str))
			gone = merge.delete_with_pricing_rules(x.item_code, allowed, log, backup)
			_set_row(x, status="Deleted" if gone else "Kept", message=None if gone else "see the log")
			log(f"leftover {x.item_code}: {'deleted' if gone else 'NOT deleted'}")
	if backup:
		_set(job, deleted_pricing_rules=json.dumps(backup, default=str))
	_step(job, "Delete leftover bad data", "done", f"{sum(x.status == 'Deleted' for x in job.leftovers)} deleted")


def _pull_legacy_images(job, log):
	"""Keep the legacy products' photography before the drop deletes it from the websites.

	Never fatal: the merge itself is done by now, and a website that cannot answer costs its own
	images rather than the job. The drop runs either way - holding it back would strand the
	products, which is the worse of the two failures.
	"""
	step = "Keep legacy product images"
	# No early return on an empty legacy list: the survivor's own product is read too, and a merge
	# that consolidated nothing still has its variants' photography to re-point.
	try:
		counts = legacy_images.pull_and_remap(job, log)
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(title=f"Item Merge Job {job.name} legacy images",
						 message=frappe.get_traceback())
		_step(job, step, "failed", message_of(e)[:300])
		log(f"FAIL legacy images: {message_of(e)}")
		return
	if not counts["products"] and not counts["skipped"] and not counts["failed"]:
		_step(job, step, "skipped", "no website product with a slug to read images from")
		return
	message = (f"{counts['images']} image row(s) from {counts['products']} product(s) · "
			   f"{counts['mapped']} mapped to a new variant")
	if counts["unmapped"]:
		message += f" · {counts['unmapped']} unmapped"
	if counts["skipped"]:
		message += f" · {counts['skipped']} product(s) skipped"
	if counts["failed"]:
		message += f" · {counts['failed']} failed"
	if counts.get("records_removed"):
		message += f" · {counts['records_removed']} old image record(s) removed"
	if counts["notes"]:
		message += " · " + "; ".join(counts["notes"][:3])
	_step(job, step, "failed" if counts["failed"] else "attention" if counts["skipped"] else "done",
		  message[:600])


def _settle_inventory(job, log):
	"""Recalculate Bins and rebuild the Item Inventory Output for every item the merge wrote to.

	`CustomItem.before_rename` deletes both items' inventory output records during a merge, because
	item_code is that doctype's autoname and unique. Nothing put them back.
	"""
	step = "Settle inventory"
	items = [p.new_item for p in (job.get("pairs") or []) if p.status == "Ok" and p.new_item]
	if not items:
		return
	try:
		counts = inventory.settle(items, log)
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(title=f"Item Merge Job {job.name} inventory", message=frappe.get_traceback())
		_step(job, step, "failed", message_of(e)[:300])
		return
	message = (f"{counts['bins']} item(s) recalculated · {counts['outputs']} inventory output(s) "
			   f"rebuilt")
	if counts["skipped"]:
		message += f" · {counts['skipped']} with no stock history"
	if counts["failed"]:
		message += f" · {counts['failed']} failed"
	if counts["notes"]:
		message += " · " + "; ".join(counts["notes"][:3])
	_step(job, step, "failed" if counts["failed"] else "done", message[:600])


def _push_to_websites(job, template, log):
	"""Send the consolidated product to the websites, by saving it with the webhooks back on.

	There is no separate upsert message: the Item `on_update` webhook is the upsert, and a merge
	runs with `in_import` set for its whole length precisely so that webhook does *not* fire on
	every half-finished step. So the push is a deliberate save at the end, with the flags put back.

	The template and its new variants, in that order - the template carries the product and the
	variants carry what hangs off it.
	"""
	step = "Push to websites"
	if not exists(template):
		return
	tdoc = frappe.get_doc("Item", template).as_dict()
	legacy = variant_attribute(tdoc)
	docs = family.load_items(family.variant_codes(template))
	new_variants = sorted(c for c, d in docs.items() if family.is_new(d, legacy))

	sent, failed = 0, []
	try:
		with with_webhooks():
			for code in [template] + new_variants:
				try:
					doc = frappe.get_doc("Item", code)
					# Never push the template's own child tables down onto its variants; each
					# variant is saved on its own right after.
					family.save_template(doc) if code == template else doc.save()
					frappe.db.commit()
					sent += 1
				except Exception as e:
					frappe.db.rollback()
					failed.append(f"{code}: {message_of(e)[:90]}")
					frappe.log_error(title=f"Item Merge push {code}", message=frappe.get_traceback())
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(title=f"Item Merge Job {job.name} push", message=frappe.get_traceback())
		_step(job, step, "failed", message_of(e)[:300])
		return

	message = f"{sent} item(s) sent ({len(new_variants)} variant(s))"
	if failed:
		message += " · " + "; ".join(failed[:3])
	log(f"pushed {sent} item(s) to the websites")
	_step(job, step, "failed" if failed else "done", message[:600])


def _push_images(job, template, log):
	"""Send the product's images to the websites, by saving its S3 Uploader record with the
	webhooks back on.

	Nothing else does it. `pull_and_remap` saves the record with the push suppressed, since it runs
	before the drops and the product push, and `_push_to_websites` only saves Items - so without
	this the sites get the merged product and none of its pictures.
	"""
	step = "Push images to websites"
	names = frappe.get_all("S3 Product Image Meta Data", filters={"nat_product_template": template},
						   order_by="creation desc", limit=1, pluck="name")
	if not names:
		_step(job, step, "skipped", f"no S3 Uploader record for {template}")
		return
	try:
		with with_webhooks():
			doc = frappe.get_doc("S3 Product Image Meta Data", names[0])
			doc.nat_skip_website_push = 0
			doc.save(ignore_permissions=True)
			frappe.db.commit()
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(title=f"Item Merge Job {job.name} images", message=frappe.get_traceback())
		_step(job, step, "failed", message_of(e)[:300])
		log(f"FAIL image push: {message_of(e)}")
		return
	message = f"{len(doc.nat_skus)} SKU(s), {len(doc.nat_images)} image row(s) sent from {doc.name}"
	log(f"pushed images: {message}")
	_step(job, step, "done", message)


def _verify_websites(job, template, log):
	"""Ask the websites what they now hold. The queue is asynchronous, so `pending` is a real answer."""
	step = "Website check"
	try:
		result = product_details.verify(template)
	except Exception as e:
		_step(job, step, "skipped", message_of(e)[:300])
		return
	_set(job, website_check=json.dumps(result, default=str))
	bad = [r for r in result["rows"] if r["status"] in ("mismatch", "error")]
	status = "failed" if bad else ("attention" if result["pending"] else "done")
	message = "; ".join(f"{r['price_list']}: {r['message']}" for r in (bad or result["rows"]))[:600]
	log(f"website check: {message[:200]}")
	_step(job, step, status, message)


def _drop_legacy_products(job, log):
	"""Remove the Storebuilder products this merge consolidated away.

	Nothing new talks to the sites here: each row inserts an Item Drop and Create Log, and the drop
	webhook that has always existed does the rest. The rows carry skip_recreate, so the confirmation
	path deletes the product instead of pushing it straight back.
	"""
	step = "Drop legacy website products"
	rows = job.get("legacy_products") or []
	if not rows:
		return
	try:
		with with_webhooks():  # the one step in a merge that is meant to reach the websites
			counts = legacy_products.issue_drops(job, log)
	except Exception as e:  # the merge itself is done; report and carry on
		frappe.db.rollback()
		frappe.log_error(title=f"Item Merge Job {job.name} legacy drops", message=frappe.get_traceback())
		_step(job, step, "failed", message_of(e)[:300])
		log(f"FAIL legacy drops: {message_of(e)}")
		return
	message = f"{counts['issued']} drop(s) issued"
	if counts["skipped"]:
		message += f" · {counts['skipped']} left alone"
	if counts["failed"]:
		message += f" · {counts['failed']} failed"
	_step(job, step, "failed" if counts["failed"] else "attention" if counts["skipped"] else "done", message)




def run_changes(job, log):
	pending = [r for r in job.changes if r.status != "Done"]
	log(f"=== {len(pending)} item change(s) under {job.template} as {frappe.session.user}")
	failed = False
	for i, r in enumerate(pending):
		_set_row(r, status="Running", message=None)
		code, new = r.item_code, r.new_code
		try:
			# a resumed row may already have been renamed
			here = new if new and not exists(code) and exists(new) else code
			if not exists(here):
				raise UserError(f"{code} no longer exists")
			updates = {k: v for k, v in (("item_name", r.new_item_name), ("ifw_retailskusuffix", r.new_retail_sku)) if v}
			if updates:
				doc = frappe.get_doc("Item", here)
				if any(doc.get(k) != v for k, v in updates.items()):
					_set_row(r, snapshot=json.dumps(doc.as_dict(), default=str))
					doc.update(updates)
					doc.save()
					frappe.db.commit()
					log(f"{here}: set {updates}")
			if new and here != new:
				if exists(new):
					raise UserError(f"{new} already exists")
				frappe.rename_doc("Item", code, new)
				frappe.db.commit()
				if not (exists(new) and not exists(code)):
					raise UserError("rename did not take effect")
				log(f"renamed {code} -> {new}")
			_set_row(r, status="Done")
		except Exception as e:  # reported on the row, then the job stops
			frappe.db.rollback()
			_set_row(r, status="Failed", message=message_of(e)[:1000])
			log(f"FAIL {code}: {message_of(e)[:300]}")
			failed = True
		_set(job, processed=sum(x.status == "Done" for x in job.changes))
		if failed:
			log("STOPPED on failure - fix the cause, then Resume; finished rows are skipped")
			break
		if new and i < len(pending) - 1:
			time.sleep(merge.MERGE_SPACING_S)
	_step(job, "Apply item changes", "failed" if failed else "done", f"{job.processed}/{len(job.changes)} done")
	_set(job, status="Failed" if failed else "Done", finished_on=now_datetime())
	log(f"=== job {job.status.lower()}")


# ---------- queue ----------

def resume(job_name):
	job = frappe.get_doc(DOCTYPE, job_name)
	_mark_interrupted(job)
	if job.status in ACTIVE:
		raise UserError("That job is already queued or running")
	running = _active_job(job.template)
	if running:
		raise UserError(f"Job {running} is already queued or running for {job.template}")
	_set(job, status="Queued", error=None, finished_on=None)
	_enqueue(job)
	return job.name


def _mark_interrupted(job):
	"""A job whose worker died (restart, timeout) stays Queued/Running for ever unless we notice."""
	if job.status not in ACTIVE:
		return
	from frappe.utils.background_jobs import is_job_enqueued

	started = job.started_on or job.creation
	if time_diff_in_seconds(now_datetime(), started) < 90:
		return
	try:
		alive = is_job_enqueued(_job_id(job.name))
	except Exception:
		return
	if not alive:
		_set(job, status="Interrupted", error="The worker stopped while this job was in progress - Resume to continue")


def list_jobs(template=None, limit=100):
	filters = {"template": ["like", f"%{template.strip()}%"]} if (template or "").strip() else {}
	jobs = frappe.get_list(DOCTYPE, filters=filters, fields=["name", "job_type", "template", "status", "total", "processed",
															  "owner", "creation", "finished_on"],
						   order_by="creation desc", limit_page_length=limit)
	names = [j.name for j in jobs]
	failed = {}
	for child in ("Item Merge Job Pair", "Item Merge Job Change"):
		for r in frappe.get_all(child, filters={"parent": ["in", names], "status": "Failed"},
								fields=["parent", "count(name) as n"], group_by="parent") if names else []:
			failed[r.parent] = failed.get(r.parent, 0) + r.n
	return [{"name": j.name, "job_type": j.job_type, "template": j.template, "status": j.status.lower(),
			 "total": j.total, "processed": j.processed, "failed": failed.get(j.name, 0), "user": j.owner,
			 "created": j.creation, "finished": j.finished_on} for j in jobs]


def job_status(job_name, live=True):
	"""The job as the page shows it, plus - live - what the items say right now."""
	job = frappe.get_doc(DOCTYPE, job_name)
	_mark_interrupted(job)
	out = {
		"name": job.name, "job_type": job.job_type, "template": job.template, "status": job.status.lower(),
		"user": job.owner, "created": job.creation, "started": job.started_on, "finished": job.finished_on,
		"error": job.error, "total": job.total, "processed": job.processed,
		"options": json.loads(job.options or "{}"), "steps": _steps(job),
		"website_check": json.loads(job.website_check or "null"),
		"log": (job.log or "").splitlines(),
		"pairs": [{"old": p.old_item, "new": p.new_item, "item_name": p.item_name, "retail_sku": p.retail_sku,
				   "status": p.status.lower(), "message": p.message, "expected_qty": p.expected_qty if p.status == "Ok" else None}
				  for p in job.pairs],
		"leftovers": [{"item_code": x.item_code, "status": x.status.lower(), "message": x.message} for x in job.leftovers],
		"legacy_products": [{"product": r.product, "lead_source": r.lead_source, "price_list": r.price_list,
							 "site": r.site, "slug": r.slug, "source": r.source, "verified": r.verified,
							 "state": r.state, "status": r.status.lower(), "drop_log": r.drop_log,
							 "message": r.message}
							for r in job.get("legacy_products") or []],
		"changes": [{"item_code": c.item_code, "new_code": c.new_code, "new_item_name": c.new_item_name,
					 "new_retail_sku": c.new_retail_sku, "status": c.status.lower(), "message": c.message} for c in job.changes],
		"live": None,
	}
	if not live:
		return out
	if job.job_type == "Item Changes":
		codes = [c["new_code"] if c["status"] == "done" and c["new_code"] else c["item_code"] for c in out["changes"]]
		docs = family.load_items(codes)
		out["live"] = {"items": [{"item_code": c, "exists": c in docs, "item_name": (docs.get(c) or {}).get("item_name"),
								  "retail_sku": (docs.get(c) or {}).get("ifw_retailskusuffix")} for c in codes]}
		return out

	olds = [p["old"] for p in out["pairs"]]
	news = [p["new"] for p in out["pairs"]]
	current = family.current_codes(news)
	still = set(frappe.get_all("Item", filters={"name": ["in", olds]}, pluck="name")) if olds else set()
	hist = set(frappe.get_all("Item Merge History", filters={"old_item_code": ["in", olds]}, pluck="old_item_code")) if olds else set()
	rep = family.reposts(job.template) if exists(job.template) else {"pending": 0, "running": 0, "failed": [], "worker": None}
	codes = [current.get(n) or n for n in news]
	docs, stock = family.load_items(codes), family.load_stock(codes)
	audit = []
	for p, code in zip(out["pairs"], codes):
		expected = p["expected_qty"]
		actual = stock.get(code, {}).get("qty", 0)
		d = docs.get(code) or {}
		audit.append({"old": p["old"], "new": p["new"], "code": code, "exists": code in docs,
					  "item_name": d.get("item_name"), "retail_sku": d.get("ifw_retailskusuffix"),
					  "old_gone": p["old"] not in still, "history": p["old"] in hist,
					  "expected_qty": expected, "actual_qty": actual,
					  "state": ("waiting" if expected is None else "ok" if abs(actual - expected) < 0.001
								else "syncing" if rep["pending"] else "mismatch")})
	out["live"] = {"old_remaining": len(still), "reposts": rep, "audit": audit}
	return out
