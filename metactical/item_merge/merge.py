"""One old variant into one new variant, in-process.

Per pair, in this order:
  snapshot -> preflight (fix new is_stock_item) -> rename_doc(merge=True) -> verify old gone and
  ledger moved -> Item Merge History (the CustomItem hook normally writes it) -> item name, retail
  SKU, duplicate supplier rows, website specs the hook wiped, Website - Camo deduct row.

What the CustomItem rename hooks already do, and this module does not repeat: barcodes, supplier
rows, website specs and item defaults from the old item, Item Price clean-up, Item Merge Settings
fields, the merge history row and the stock reposts.
"""
import json
import time

import frappe

from metactical.item_merge import catalogue, rules
from metactical.item_merge.family import exists, message_of

MERGE_SPACING_S = 1.5  # measured: zero repost deadlocks across ~800 reposts at this spacing
# The rename hook keeps working on the new item after rename_doc returns: it commits as it goes and
# enqueues the reposts. Saving the follow-ups straight away races it, which MariaDB reports as a
# deadlock and Frappe as "Document has been modified after you have opened it". The stand-alone app
# waited for the hook's Item Merge History row before touching the item; in-process the equivalent
# is to re-read the item and try again.
FOLLOW_UP_ATTEMPTS = 6
FOLLOW_UP_BACKOFF_S = 0.75
CONTENDED = (frappe.TimestampMismatchError, frappe.QueryDeadlockError)


def bins(code):
	return frappe.get_all("Bin", filters={"item_code": code}, fields=["warehouse", "actual_qty", "stock_value"])


def qty(rows):
	return sum(b.get("actual_qty") or 0 for b in rows)


def ledger_count(code):
	return frappe.db.count("Stock Ledger Entry", {"item_code": code, "is_cancelled": 0})


def _plan_follow_ups(after, od, pair, fix_names, sku, specs_before):
	"""Everything the merge leaves for us to set on the new item, applied to a freshly read doc.
	Returns the labels of what changed and how many duplicate supplier rows were dropped."""
	changed = []
	# a pair can carry the exact name / retail SKU chosen on the align screen
	want_name = (pair.get("item_name") or "").strip() or (od.item_name if fix_names else None)
	if want_name and after.item_name != want_name:
		after.item_name = want_name
		changed.append("name")
	want_sku = (pair.get("retail_sku") or "").strip() or (after.name if sku == "code" else None)
	if want_sku and after.get("ifw_retailskusuffix") != want_sku:
		after.ifw_retailskusuffix = want_sku
		changed.append("retail sku")
	suppliers = after.get("supplier_items") or []
	kept = rules.dedupe_suppliers([r.as_dict() for r in suppliers])
	removed = len(suppliers) - len(kept)
	if removed:
		keep_names = {r["name"] for r in kept}
		after.set("supplier_items", [r for r in suppliers if r.name in keep_names])
		changed.append("suppliers")
	if not after.get("neb_website_specifications") and specs_before:
		# the hook replaces the new item's specs with the old item's, even when the old had none
		for r in specs_before:
			after.append("neb_website_specifications", r)
		changed.append("website specs")
	# Which sites need a deduct row is read from ERPNext, not assumed: the Lead Source of each price
	# list the family actually sells on. It used to be the literal "Website - Camo" on every item,
	# which is a Link - so on a site without that record every single pair failed.
	have = {r.lead_source for r in after.get("custom_neb_website_deduct_qty") or []}
	for lead_source in catalogue.deduct_lead_sources(after.name, after.variant_of):
		if lead_source in have:
			continue
		# qty 0 is the house default; a non-zero buffer is a deliberate per-product decision made later
		after.append("custom_neb_website_deduct_qty", {"lead_source": lead_source, "qty": 0})
		changed.append(f"deduct row ({lead_source})")
	return changed, removed


def _apply_follow_ups(new, od, pair, fix_names, sku, specs_before, log):
	"""Save the follow-ups, standing out of the rename hook's way.

	The hook is still writing to this item when rename_doc returns, so a save can lose a race with
	it. Each attempt re-reads the item, so a retry applies to whatever the hook has left behind
	rather than overwriting it from a stale copy."""
	for attempt in range(1, FOLLOW_UP_ATTEMPTS + 1):
		after = frappe.get_doc("Item", new)
		changed, removed = _plan_follow_ups(after, od, pair, fix_names, sku, specs_before)
		if not changed:
			return after, changed, removed
		try:
			after.save()
			frappe.db.commit()
			return after, changed, removed
		except CONTENDED as e:
			frappe.db.rollback()
			if attempt == FOLLOW_UP_ATTEMPTS:
				raise
			log(f"    {new}: the rename hook still holds the item ({type(e).__name__}) - "
				f"retry {attempt}/{FOLLOW_UP_ATTEMPTS - 1}")
			time.sleep(FOLLOW_UP_BACKOFF_S * attempt)


def merge_pair(pair, log, fix_names=True, sku="keep"):
	"""Merge pair.old into pair.new. pair: dict with old, new and optionally item_name / retail_sku
	chosen on the align screen. Returns (status, details) where status is ok / skipped / failed."""
	old, new = pair["old"], pair["new"]
	if not exists(old):
		log(f"SKIP {old}: already merged")
		return "skipped", {}
	od, nd = frappe.get_doc("Item", old), frappe.get_doc("Item", new)
	ob, nb = bins(old), bins(new)
	details = {"snapshot": json.dumps({"doc": od.as_dict(), "bins": ob, "new_before": nd.as_dict(), "new_bins_before": nb},
									  default=str),
			   "old_qty": qty(ob), "new_qty_before": qty(nb), "expected_qty": qty(ob) + qty(nb)}

	issues, fixes = rules.preflight(od.as_dict(), nd.as_dict())
	if issues:
		log(f"FAIL {old} -> {new}: preflight {issues}")
		return "failed", {**details, "message": f"preflight: {'; '.join(issues)}"}
	if fixes:
		nd.update(fixes)
		nd.save()
	specs_before = [{"label": r.label, "description": r.description, "mandatory": r.mandatory}
					for r in nd.get("neb_website_specifications") or []]
	log(f"--- {old} -> {new}  qty {qty(ob):g}{'  (is_stock_item fixed on new)' if fixes else ''}")

	frappe.rename_doc("Item", old, new, merge=True)
	frappe.db.commit()  # the hooks commit part of their work themselves; make the merge itself durable too

	if exists(old):
		log(f"FAIL {old}: still exists after merge")
		return "failed", {**details, "message": "old item still exists after the merge"}
	if ledger_count(old):
		log(f"FAIL {old}: ledger rows still on the old code")
		return "failed", {**details, "message": "stock ledger rows are still on the old code"}

	after, changed, removed = _apply_follow_ups(new, od, pair, fix_names, sku, specs_before, log)

	if not frappe.db.exists("Item Merge History", {"old_item_code": old}):
		frappe.get_doc({"doctype": "Item Merge History", "old_item_code": old, "new_item_code": new,
						"old_item": json.dumps(od.as_dict(), default=str),
						"new_item": json.dumps(after.as_dict(), default=str)}).insert(ignore_permissions=True)
		history = "created"
	else:
		history = "hook"
	frappe.db.commit()
	log(f"    OK  history {history} · {', '.join(changed) or 'no follow-up changes'} · "
		f"{removed} duplicate supplier row(s) removed · sku {after.get('ifw_retailskusuffix')} · "
		f"expect qty {details['expected_qty']:g} once reposts drain")
	return "ok", details


def delete_with_pricing_rules(code, allowed, log, backup):
	"""Delete an item, clearing only per-item Pricing Rules whose every row is in `allowed`.
	526k per-item Pricing Rules exist on the dev site, mostly expired; each blocks its item's deletion."""
	for _ in range(15):
		frappe.db.savepoint("item_merge_delete")
		try:
			frappe.delete_doc("Item", code)
			frappe.db.commit()
			return True
		except Exception as e:
			frappe.db.rollback(save_point="item_merge_delete")
			text = message_of(e)
			rule = rules.pricing_rule_blocker(text)
			if not rule or not frappe.db.exists("Pricing Rule", rule):
				log(f"  cannot delete {code}: {text[:200]}")
				return False
			rule_items = frappe.get_all("Pricing Rule Item Code", filters={"parent": rule}, pluck="item_code")
			outside = [c for c in rule_items if c not in allowed]
			if outside:
				log(f"  kept {code}: {rule} also prices {outside[:3]}")
				return False
			backup.append(frappe.get_doc("Pricing Rule", rule).as_dict())
			frappe.delete_doc("Pricing Rule", rule)
			frappe.db.commit()
			log(f"  {code}: deleted per-item Pricing Rule {rule} (backed up on the job)")
	return False
