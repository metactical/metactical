"""The shared logger for the GearStock jobs: sites/<site>/logs/gearstock.log.

Each step logs every item, in the order the steps run:
  [Item Upsert]  upsert_items_v7, every row in gearstock_items.json
  [Image Push]   push_images, every template and standalone item
  [Inventory]    add_deduct_qty, every row in gearstock_items.json

Frappe sets new loggers to ERROR outside the dev server, which would drop every progress line,
so the level is set to INFO here. Files rotate at MAX_SIZE, keeping FILE_COUNT old ones: a full
run writes several MB, more than Frappe's 100 KB default would keep.
"""

import logging

import frappe

MAX_SIZE = 20 * 1024 * 1024  # bytes per file
FILE_COUNT = 10


def get_logger():
	logger = frappe.logger("gearstock", allow_site=True, max_size=MAX_SIZE, file_count=FILE_COUNT)
	logger.setLevel(logging.INFO)
	return logger
