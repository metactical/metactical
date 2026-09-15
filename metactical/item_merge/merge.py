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

import frappe

from metactical.item_merge import rules
from metactical.item_merge.family import exists, message_of

DEDUCT_LEAD = "Website - Camo"
MERGE_SPACING_S = 1.5  # measured: zero repost deadlocks across ~800 reposts at this spacing


def bins(code):
	return frappe.get_all("Bin", filters={"item_code": code}, fields=["warehouse", "actual_qty", "stock_value"])


def qty(rows):
	return sum(b.get("actual_qty") or 0 for b in rows)


def ledger_count(code):
	return frappe.db.count("Stock Ledger Entry", {"item_code": code, "is_cancelled": 0})


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

	after = frappe.get_doc("Item", new)
	changed = []
	# a pair can carry the exact name / retail SKU chosen on the align screen
	want_name = (pair.get("item_name") or "").strip() or (od.item_name if fix_names else None)
	if want_name and after.item_name != want_name:
		after.item_name = want_name
		changed.append("name")
	want_sku = (pair.get("retail_sku") or "").strip() or (new if sku == "code" else None)
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
	if not any(r.lead_source == DEDUCT_LEAD for r in after.get("custom_neb_website_deduct_qty") or []):
		# qty 0 is the house default; a non-zero buffer is a deliberate per-product decision made later
		after.append("custom_neb_website_deduct_qty", {"lead_source": DEDUCT_LEAD, "qty": 0})
		changed.append("deduct row")
	if changed:
		after.save()

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
