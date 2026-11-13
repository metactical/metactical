"""Move items to the item group suggested in ERP_Item_Group.xlsx.

item_groups.json (next to this file) is the sheet's Item Code and Suggested Item Group columns. For
each row the item is saved with the new group, so validation, on_update and the Item webhooks run
and the websites get the new category.

Each row is checked first, and skipped with a reason in the log when:
  - the item is not in ERPNext
  - the item group is not in ERPNext
  - the item group is a group node (items can only go in a leaf group)
An item that is already in the group is still saved, so its webhook fires too; the log says the
group was already correct.

Frappe drops webhooks while a patch or migrate is running, so the patch only queues the job and
the job waits for the migrate to finish before it starts. Rows go in batches of BATCH_SIZE with
BATCH_DELAY seconds between batches, committing after each item; a deadlock or lock wait is
retried (gearstock.db_retry). Progress goes to sites/<site>/logs/item_group_update.log, and a
summary with every skipped row goes to the Error Log.

Safe to re-run by hand: bench --site <site> execute metactical.patches.item_group.update_item_groups.run
Resume part way with --kwargs "{'start': <row index>}".
"""

import json
import logging
import os
import time

import frappe
from frappe.utils.synchronization import filelock

from metactical.patches.gearstock import db_retry

DATA_FILE = os.path.join(os.path.dirname(__file__), "item_groups.json")
JOB_ID = "update_item_groups"
BATCH_SIZE = 500
BATCH_DELAY = 10  # seconds between batches
MIGRATE_WAIT = 60 * 60  # seconds
LOG_PREFIX = "[Item Group Update]"

# reason key -> log text
REASONS = {
	"item_not_found": "item not found in ERPNext",
	"group_not_found": "item group not found in ERPNext",
	"group_is_parent": "item group is a group node, items can only be assigned to a leaf group",
}


def execute():
	start()


def start():
	"""Queue the update in a worker, so the item saves fire the webhooks."""
	frappe.enqueue(
		"metactical.patches.item_group.update_item_groups.run",
		queue="default",
		timeout=24 * 60 * 60,
		job_id=JOB_ID,
		deduplicate=True,
		enqueue_after_commit=True,
	)


def get_logger():
	"""sites/<site>/logs/item_group_update.log. Frappe sets new loggers to ERROR outside the dev
	server, which would drop the progress lines, so the level is set to INFO."""
	logger = frappe.logger(
		"item_group_update", allow_site=True, max_size=20 * 1024 * 1024, file_count=10
	)
	logger.setLevel(logging.INFO)
	return logger


def load_rows():
	with open(DATA_FILE) as f:
		return json.load(f)


def wait_for_migrate():
	"""Wait until the migrate that queued this job has finished. Saving items while migrate alters
	tabItem deadlocks; migrate holds this lock from start to end."""
	with filelock("bench_migrate", timeout=MIGRATE_WAIT):
		pass


def run(start=0):
	logger = get_logger()
	wait_for_migrate()

	rows = load_rows()
	groups = {
		g.name: g.is_group for g in frappe.get_all("Item Group", fields=["name", "is_group"])
	}
	counts = frappe._dict(updated=0, already_in_group=0, failed=0, **dict.fromkeys(REASONS, 0))
	skipped, failed = [], []
	total = len(rows)
	logger.info(f"{LOG_PREFIX} Started at row {int(start) + 1} of {total}")

	for offset in range(int(start), total, BATCH_SIZE):
		for index, row in enumerate(rows[offset : offset + BATCH_SIZE], start=offset + 1):
			update_row(row, groups, counts, skipped, failed, logger, f"{index}/{total}")

		end = min(offset + BATCH_SIZE, total)
		logger.info(f"{LOG_PREFIX} Batch completed: rows {offset + 1}-{end} of {total}, totals {dict(counts)}")
		if end < total:
			time.sleep(BATCH_DELAY)

	logger.info(f"{LOG_PREFIX} Completed: totals {dict(counts)}, failed {failed}")
	frappe.log_error(
		title="Item group update finished",
		message=json.dumps({"counts": counts, "skipped": skipped, "failed": failed}, indent=1),
	)


def check_row(item_code, item_group, current_group, groups):
	"""The reasons the row cannot be applied, empty when it can. Both a missing item and a missing
	group are reported together."""
	reasons = []
	if current_group is None:
		reasons.append("item_not_found")
	if item_group not in groups:
		reasons.append("group_not_found")
	elif groups[item_group]:
		reasons.append("group_is_parent")
	return reasons


def update_row(row, groups, counts, skipped, failed, logger, position):
	item_code, item_group = row["item_code"], row["item_group"]
	label = f"{LOG_PREFIX} ({position}) Item {item_code} -> Item Group '{item_group}'"

	current_group = frappe.db.get_value("Item", item_code, "item_group")
	reasons = check_row(item_code, item_group, current_group, groups)
	if reasons:
		for reason in reasons:
			counts[reason] += 1
		text = "; ".join(REASONS[reason] for reason in reasons)
		skipped.append({"item_code": item_code, "item_group": item_group, "reason": text})
		logger.warning(f"{label}: skipped, {text}")
		return

	try:
		db_retry.run(lambda: save_item(item_code, item_group))
		if current_group == item_group:
			counts.already_in_group += 1
			logger.info(f"{label}: saved, item group was already correct")
		else:
			counts.updated += 1
			logger.info(f"{label}: updated from '{current_group}'")
	except Exception:
		db_retry.rollback_item()
		counts.failed += 1
		failed.append(item_code)
		frappe.log_error(title=f"Item group update failed: {item_code}", message=frappe.get_traceback())
		logger.error(f"{label}: failed, changes rolled back, see the Error Log")


def save_item(item_code, item_group):
	item = frappe.get_doc("Item", item_code)
	item.item_group = item_group
	# Only the items in the sheet change: without this, saving a template copies its fields onto
	# every variant (Item Variant Settings).
	item.flags.dont_update_variants = True
	item.save()
	frappe.db.commit()
