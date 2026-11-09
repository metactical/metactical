"""Push the GearStock images again, on their own: no item upsert, no Website Deduct Qty.

Some items reached GearStock without their images. This runs push_images over the same catalogue
with force on, so every item's S3 Product Image Meta Data record is saved and pushed even when
nothing on it changed, and the webhook sends its images to GearStock again. It stops after the
last image batch: add_deduct_qty is not queued, so no inventory update goes out.

Items with no images on Camo are still skipped and listed in gearstock_images_report.csv.
Progress goes to the "gearstock" log (sites/<site>/logs/gearstock.log).

The patch only queues the job, which waits for migrate to finish before it starts.

Safe to re-run by hand:
	bench --site <site> execute metactical.patches.gearstock.push_images.run --kwargs "{'force': True, 'then_deduct': False}"
"""

import frappe

from metactical.patches.gearstock import push_images
from metactical.patches.gearstock.upsert_items_v7 import PRICE_LIST


def execute():
	if not frappe.db.exists("Price List", PRICE_LIST):
		return

	push_images.start(force=True, then_deduct=False)
