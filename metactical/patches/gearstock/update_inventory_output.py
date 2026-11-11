"""Queue the inventory update for every item in the GearStock catalogue (gearstock_items.json).

For each item it queues the same job Item.on_update queues when Website Deduct Qty changes:
	frappe.enqueue(update_item_inventory_output, item_code=..., voucher_type="Item", queue="default")
Nothing on the items is changed.

The patch only queues a runner job, because the inventory update fires webhooks and Frappe drops
webhooks while a migrate is running. The runner waits for the migrate to finish, then queues the
items in batches of BATCH_SIZE with a BATCH_DELAY wait between batches, so the default queue and
the websites are not flooded. An item that is not in ERPNext, or fails to queue, is skipped and
logged without stopping the batch. Progress goes to the
"gearstock_inventory_output" log (sites/<site>/logs/gearstock_inventory_output.log), separate
from the gearstock.log the upsert_items patch writes.

Safe to re-run by hand: bench --site <site> execute metactical.patches.gearstock.update_inventory_output.run
To pick up from a batch, pass its start from the log, e.g. --kwargs "{'start': 3000}".
"""

import json
import logging
import os
import time

import frappe
from frappe.utils.synchronization import filelock

from metactical.metactical.doctype.item_inventory_output.item_inventory_output import (
	update_item_inventory_output,
)

DATA_FILE = os.path.join(os.path.dirname(__file__), "gearstock_items.json")
BATCH_SIZE = 1000
BATCH_DELAY = 10  # seconds between batches
JOB_ID = "gearstock_update_inventory_output"
MIGRATE_WAIT = 60 * 60  # seconds


def execute():
	frappe.enqueue(
		"metactical.patches.gearstock.update_inventory_output.run",
		queue="default",
		timeout=6 * 60 * 60,
		job_id=JOB_ID,
		deduplicate=True,
		enqueue_after_commit=True,
	)


def get_logger():
	logger = frappe.logger("gearstock_inventory_output", allow_site=True, max_size=20 * 1024 * 1024, file_count=10)
	# Frappe sets new loggers to ERROR outside the dev server, which would drop the progress lines.
	logger.setLevel(logging.INFO)
	return logger


def get_item_codes():
	"""Every item code in the catalogue, in file order, without duplicates."""
	with open(DATA_FILE) as f:
		return list(dict.fromkeys(row["item_code"] for row in json.load(f)))


def run(start=0):
	logger = get_logger()

	# Migrate holds this lock from start to end; wait so the webhooks the updates fire are not dropped.
	with filelock("bench_migrate", timeout=MIGRATE_WAIT):
		pass

	codes = get_item_codes()
	logger.info(f"[Inventory] Started at item {int(start) + 1} of {len(codes)}")

	queued, missing, failed = 0, [], []
	for offset in range(int(start), len(codes), BATCH_SIZE):
		batch = codes[offset : offset + BATCH_SIZE]
		for index, item_code in enumerate(batch, start=offset + 1):
			# One bad item is logged and skipped; it never stops the batch.
			if not frappe.db.exists("Item", item_code):
				missing.append(item_code)
				logger.warning(f"[Inventory] {item_code}: skipped, item not found in ERPNext ({index}/{len(codes)})")
				continue
			try:
				frappe.enqueue(
					update_item_inventory_output, item_code=item_code, voucher_type="Item", queue="default"
				)
				queued += 1
			except Exception:
				failed.append(item_code)
				logger.error(f"[Inventory] {item_code}: failed to queue ({index}/{len(codes)}), see the Error Log")
				frappe.log_error(
					title=f"GearStock inventory update failed to queue: {item_code}", message=frappe.get_traceback()
				)

		logger.info(
			f"[Inventory] Batch done: {offset + len(batch)}/{len(codes)} items, "
			f"totals queued {queued}, not in ERPNext {len(missing)}, failed {len(failed)}"
		)
		if offset + BATCH_SIZE < len(codes):
			time.sleep(BATCH_DELAY)

	logger.info(
		f"[Inventory] Completed: {queued} item(s) queued, {len(missing)} not in ERPNext {missing}, "
		f"{len(failed)} failed {failed}"
	)
	frappe.log_error(
		title="GearStock inventory update queued",
		message=json.dumps({"queued": queued, "missing": missing, "failed": failed}, indent=1),
	)
