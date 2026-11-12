"""Catalogue items that were merged into other items in ERPNext.

Some rows in gearstock_items_not_in_erp.json name items that were later merged (or renamed) into
another item, so their code no longer exists. Item Merge History records where each one went.
upsert_items looks them up once per run, logs them and saves the map to MAP_FILE, so push_images
and add_deduct_qty can read the map instead of searching the history again.
"""

import json
import os
from collections import defaultdict

import frappe

MAP_FILE = os.path.join(os.path.dirname(__file__), "gearstock_merged_items.json")


def build(rows, logger):
	"""Map each row code that is not an Item to the existing item it was merged into, write it to
	MAP_FILE and log it. Codes with no merge history (or whose chain ends nowhere) are left out."""
	from metactical.item_merge.family import current_codes

	codes = list(dict.fromkeys(row["item_code"] for row in rows))
	existing = set(frappe.get_all("Item", filters={"name": ["in", codes]}, pluck="name")) if codes else set()
	missing = [code for code in codes if code not in existing]

	resolved = current_codes(missing) if missing else {}
	targets = {new for old, new in resolved.items() if new != old}
	found = set(frappe.get_all("Item", filters={"name": ["in", list(targets)]}, pluck="name")) if targets else set()

	mapping, merged_into = {}, defaultdict(list)
	for old in missing:
		new = resolved.get(old, old)
		if new != old and new in found:
			mapping[old] = new
			merged_into[new].append(old)
		else:
			logger.warning(f"[Item Merge] {old}: not found and no merge history")

	for new, olds in merged_into.items():
		logger.info(f"[Item Merge] {', '.join(olds)} merged into {new}")
	logger.info(
		f"[Item Merge] {len(mapping)} of {len(missing)} missing item(s) found in merge history, "
		f"onto {len(merged_into)} item(s), saved to {MAP_FILE}"
	)

	with open(MAP_FILE, "w") as f:
		json.dump(mapping, f, indent=1)
	return mapping


def load():
	"""The map upsert_items saved, or None if it has not run yet."""
	if not os.path.exists(MAP_FILE):
		return None
	with open(MAP_FILE) as f:
		return json.load(f)


def get(rows, logger):
	"""The saved map, or a fresh one when steps 2 and 3 run without step 1."""
	mapping = load()
	return build(rows, logger) if mapping is None else mapping


def resolve(code, mapping):
	return mapping.get(code, code)
