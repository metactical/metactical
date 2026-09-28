# Copyright (c) 2026, International Camouflage Ltd
"""Endpoints behind the Price Revision grid (/app/price-grid/<revision>).

The grid is the working surface; the Price Revision document stays the record.
Every save goes through the document's own validate(), so the maths, the
typed-price rules and the summary are the same whichever screen made the edit.
"""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import cint, flt

from metactical.icl_pricing.doctype.price_revision.price_revision import (
	apply_revision,
	revert_revision,
)
from metactical.pricing import jobs
from metactical.pricing.build import from_confirmation

SOC3 = "Supplier Order Confirmation V3"


# ------------------------------------------------------------------ opening


@frappe.whitelist()
def open_for_confirmation(confirmation, new=0):
	"""The revision to open from a supplier confirmation.

	Reuses the latest live revision for the confirmation, so clicking the
	button twice never makes two drafts. A reverted one is history, so the
	next click starts fresh; ``new=1`` forces a fresh one regardless.
	"""
	frappe.has_permission(SOC3, "read", confirmation, throw=True)
	if not cint(new):
		existing = frappe.get_all(
			"Price Revision",
			filters={
				"supplier_order_confirmation": confirmation,
				"docstatus": ("<", 2),
				"status": ("!=", "Reverted"),
			},
			pluck="name",
			order_by="creation desc",
			limit=1,
		)
		if existing:
			return existing[0]
	return from_confirmation(confirmation)


@frappe.whitelist()
def revisions_for_confirmation(confirmation):
	"""Shown on the confirmation form, newest first."""
	return frappe.get_all(
		"Price Revision",
		filters={"supplier_order_confirmation": confirmation, "docstatus": ("<", 2)},
		fields=["name", "status", "total_price_changes", "lines_needing_review", "applied_on"],
		order_by="creation desc",
	)


# ----------------------------------------------------------------- the grid
#
# Every change to a draft goes through _change(). A small revision is changed
# and saved in the request, as before. A large one (ICL Pricing Settings ->
# Run In Background Above) is handed to a background job and the endpoint
# returns {"queued": True}; the grid shows the job's progress and reloads when
# it finishes. The same change functions (CHANGES) run in both cases.


@frappe.whitelist()
def get_grid(name):
	doc = frappe.get_doc("Price Revision", name)
	doc.check_permission("read")
	if doc.docstatus == 0 and not jobs.is_busy(name) and not jobs.is_large(len(doc.items)):
		# A draft can sit for days; show it against today's prices and
		# settings. Nothing is written until the next save. (Skipped for a
		# large revision, where it would make opening it slow.)
		doc.set_currencies()
		doc.recalculate()
		doc.roll_up_summary()
	return _grid(doc)


@frappe.whitelist()
def job_state(name):
	frappe.has_permission("Price Revision", "read", name, throw=True)
	return frappe.db.get_value(
		"Price Revision", name, ["job_status", "job_operation", "job_progress", "job_message", "status", "docstatus"],
		as_dict=True,
	)


@frappe.whitelist()
def save_grid(name, cells=None, items=None):
	"""Write grid edits back to the revision.

	``cells``: [{item_code, price_list, new_price?, remove?}]. ``new_price``
	null or 0 clears a hand-set price, putting the cell back on its suggestion;
	a price for an item not yet on the list adds it. ``remove`` 1/0 marks the
	item's price on that list for deletion, or unmarks it.
	``items``: [{item_code, new_cost, apply}] — a cost change reprices the row.
	"""
	return _change(name, "edits", cells=_parse(cells), items=_parse(items))


@frappe.whitelist()
def set_whole_order(name, on):
	"""The Whole PO toggle: every line of the order, or only cost changes."""
	if not frappe.db.get_value("Price Revision", name, "supplier_order_confirmation"):
		frappe.throw(_("Only a revision from a supplier confirmation has an order to pull in."))
	return _change(name, "whole_order", on=cint(on))


@frappe.whitelist()
def set_use_suggested(name, on):
	"""The Use Suggested Price switch. Hand-set prices are never touched."""
	return _change(name, "use_suggested", on=cint(on))


@frappe.whitelist()
def add_price_list(name, price_list):
	"""Add a column: every item gets a cell on ``price_list``."""
	if not frappe.db.get_value("Price List", price_list, "enabled"):
		frappe.throw(_("{0} is not an enabled price list.").format(price_list))
	if price_list == frappe.db.get_value("Price Revision", name, "buying_price_list"):
		frappe.throw(_("{0} is the supplier's cost list; the Cost column already covers it.").format(price_list))
	return _change(name, "add_list", price_list=price_list)


@frappe.whitelist()
def drop_price_list(name, price_list):
	"""Take a column out of this revision. Prices on the list are not touched."""
	from metactical.icl_pricing.doctype.icl_pricing_settings.icl_pricing_settings import (
		always_price_lists,
	)

	if price_list in always_price_lists():
		frappe.throw(_("{0} is always included (ICL Pricing Settings).").format(price_list))
	return _change(name, "drop_list", price_list=price_list)


@frappe.whitelist()
def selectable_price_lists(name):
	"""Selling lists not yet on the revision, for the Add Price List picker."""
	have = set(frappe.get_all("Price Revision Price List", filters={"parent": name}, pluck="price_list"))
	have.add(frappe.db.get_value("Price Revision", name, "buying_price_list"))
	return [
		r for r in frappe.get_all(
			"Price List", filters={"enabled": 1, "selling": 1}, fields=["name", "currency"], order_by="name",
		)
		if r.name not in have
	]


@frappe.whitelist()
def apply_grid(name):
	"""Submit (if still a draft) and write the prices, in one step."""
	frappe.has_permission("Price Revision", "submit", name, throw=True)
	jobs.ensure_idle(name)
	if _is_large(name):
		jobs.start(name, "apply")
		return {"queued": True}
	doc = frappe.get_doc("Price Revision", name)
	if doc.docstatus == 0:
		doc.submit()
	result = apply_revision(name)
	result["grid"] = _grid(frappe.get_doc("Price Revision", name))
	return result


@frappe.whitelist()
def revert_grid(name):
	frappe.has_permission("Price Revision", "submit", name, throw=True)
	jobs.ensure_idle(name)
	if _is_large(name):
		jobs.start(name, "revert")
		return {"queued": True}
	result = revert_revision(name)
	result["grid"] = _grid(frappe.get_doc("Price Revision", name))
	return result


def _is_large(name):
	return jobs.is_large(frappe.db.count("Price Revision Item", {"parent": name}))


def _change(name, change, **kw):
	frappe.has_permission("Price Revision", "write", name, throw=True)
	docstatus, status = frappe.db.get_value("Price Revision", name, ["docstatus", "status"])
	if docstatus != 0:
		frappe.throw(_("{0} is {1}; only a draft can be edited.").format(name, status))
	jobs.ensure_idle(name)
	if _is_large(name):
		jobs.start(name, "edit", change=change, **kw)
		return {"queued": True}
	doc = frappe.get_doc("Price Revision", name)
	CHANGES[change](doc, **kw)
	doc.save()
	return _grid(doc)


# ------------------------------------------------------------ the changes


def _edits(doc, cells=None, items=None):
	by_cell = {(p.item_code, p.price_list): p for p in doc.prices}
	scoped = {d.price_list for d in doc.price_lists}
	on_revision = {i.item_code for i in doc.items}
	for c in cells or []:
		key = (c.get("item_code"), c.get("price_list"))
		row = by_cell.get(key)
		if "new_price" in c:
			price = flt(c.get("new_price"))
			if row:
				row.edited = 1 if price > 0 else 0
				if price > 0:
					row.new_price = price
			elif price > 0 and key[0] in on_revision and key[1] in scoped:
				# a price for an item that isn't on this list yet
				by_cell[key] = doc.append("prices", {
					"item_code": key[0], "price_list": key[1], "new_price": price, "edited": 1,
				})
		if "remove" in c and row:
			row.remove = cint(c.get("remove"))

	by_item = {i.item_code: i for i in doc.items}
	for it in items or []:
		row = by_item.get(it.get("item_code"))
		if not row:
			continue
		if it.get("new_cost") is not None and flt(it["new_cost"]) > 0:
			row.new_cost = flt(it["new_cost"])
		if it.get("apply") is not None:
			row.apply = cint(it["apply"])


def _whole_order(doc, on):
	from metactical.pricing.build import set_whole_order

	set_whole_order(doc, cint(on))


def _use_suggested(doc, on):
	doc.use_suggested = 1 if cint(on) else 0


def _add_list(doc, price_list):
	row = next((d for d in doc.price_lists if d.price_list == price_list), None)
	if row:
		row.include_all = 1
	else:
		doc.append("price_lists", {"price_list": price_list, "include_all": 1})


def _drop_list(doc, price_list):
	doc.set("price_lists", [d for d in doc.price_lists if d.price_list != price_list])


CHANGES = {
	"edits": _edits,
	"whole_order": _whole_order,
	"use_suggested": _use_suggested,
	"add_list": _add_list,
	"drop_list": _drop_list,
}


# ------------------------------------------------------------------ helpers


def _parse(value):
	if not value:
		return []
	if isinstance(value, str):
		value = json.loads(value)
	return value


def _short(price_list):
	return price_list[6:] if price_list.startswith("RET - ") else price_list


def _grid(doc):
	lists_in_use = {p.price_list for p in doc.prices}
	# keep the order the revision was scoped in, and drop lists nobody is on,
	# unless the list prices every item (always included, or added here)
	order = [
		d.price_list for d in doc.price_lists
		if d.price_list in lists_in_use or d.include_all
	]

	currency = dict(frappe.get_all(
		"Price List", filters={"name": ("in", order or [""])}, fields=["name", "currency"],
		as_list=True,
	))
	pair = {
		r.selling_price_list: r
		for r in frappe.get_all(
			"Pricing Matrix",
			filters={
				"buying_price_list": doc.buying_price_list,
				"selling_price_list": ("in", order or [""]),
				"brand": ("is", "not set"),
				"item_group": ("is", "not set"),
				"disabled": 0,
			},
			fields=["selling_price_list", "markup", "min_margin_pct", "sample_size", "low_confidence"],
		)
	}

	from metactical.icl_pricing.doctype.icl_pricing_settings.icl_pricing_settings import (
		always_price_lists,
	)
	from metactical.pricing.costing import LOW_MARGIN_PRICE_LISTS

	from metactical.icl_pricing.doctype.icl_pricing_settings.icl_pricing_settings import column_order

	# the settings' column order first, then the rest as scoped
	first = column_order()
	order.sort(key=lambda pl: first.index(pl) if pl in first else len(first))

	always = set(always_price_lists())
	every_item = {d.price_list for d in doc.price_lists if d.include_all} | always
	lists = []
	for pl in order:
		mx = pair.get(pl) or {}
		lists.append({
			"name": pl,
			"label": _short(pl),
			"currency": currency.get(pl),
			"markup": flt(mx.get("markup")) or None,
			"floor": flt(mx.get("min_margin_pct")) or None,
			"sample_size": mx.get("sample_size"),
			"low_confidence": cint(mx.get("low_confidence")),
			"exempt": 1 if pl in LOW_MARGIN_PRICE_LISTS else 0,
			"always": 1 if pl in always else 0,
			"every_item": 1 if pl in every_item else 0,
		})

	item_fields = ["name", "item_name", "brand", "item_group"]
	if frappe.get_meta("Item").has_field("ifw_retailskusuffix"):  # metactical's retail SKU
		item_fields.append("ifw_retailskusuffix as retail_sku")
	meta = {
		r.name: r
		for r in frappe.get_all(
			"Item",
			filters={"name": ("in", [i.item_code for i in doc.items] or [""])},
			fields=item_fields,
		)
	}

	cells = {}
	for p in doc.prices:
		cells.setdefault(p.item_code, {})[p.price_list] = {
			"old": flt(p.old_price),
			"new": flt(p.new_price),
			"suggested": flt(p.suggested_price) or None,
			"by_matrix": flt(p.suggested_by_matrix) or None,
			"by_margin": flt(p.suggested_by_margin) or None,
			"landed": flt(p.landed_in_list_ccy),
			"old_margin": p.old_margin_pct,
			"new_margin": p.new_margin_pct,
			"markup": flt(p.markup_used) or None,
			"markup_source": p.markup_source,
			"action": p.action,
			"note": p.note,
			"edited": cint(p.edited),
			"remove": cint(p.remove),
			"below_floor": cint(p.below_floor),
			"exempt": cint(p.low_margin_exempt),
		}

	rows = []
	for i in doc.items:
		m = meta.get(i.item_code) or {}
		rows.append({
			"item_code": i.item_code,
			"item_name": m.get("item_name") or i.item_name,
			"brand": m.get("brand"),
			"item_group": m.get("item_group"),
			"retail_sku": m.get("retail_sku"),
			"old_cost": flt(i.old_cost),
			"new_cost": flt(i.new_cost),
			"cost_change_pct": flt(i.cost_change_pct),
			"duty_pct": flt(i.duty_pct),
			"landed_old": flt(i.landed_old_cad),
			"landed_new": flt(i.landed_new_cad),
			"landed_old_usd": flt(i.landed_old_usd) or None,
			"landed_new_usd": flt(i.landed_new_usd) or None,
			"apply": cint(i.apply),
			"cells": cells.get(i.item_code, {}),
		})

	return {
		"doc": {
			"name": doc.name,
			"status": doc.status,
			"docstatus": doc.docstatus,
			"editable": doc.docstatus == 0 and frappe.has_permission("Price Revision", "write", doc),
			"can_apply": frappe.has_permission("Price Revision", "submit", doc),
			"supplier": doc.supplier,
			"supplier_name": doc.supplier_name or doc.supplier,
			"source": doc.source,
			"whole_order": cint(doc.whole_order),
			"job_status": doc.get("job_status") or "",
			"job_operation": doc.get("job_operation"),
			"job_progress": flt(doc.get("job_progress")),
			"job_message": doc.get("job_message"),
			"background_threshold": jobs.limits()["threshold"],
			"use_suggested": cint(doc.use_suggested),
			"order_lines": frappe.db.count("Purchase Order V3 Item", {"parent": frappe.db.get_value(SOC3, doc.supplier_order_confirmation, "purchase_order_v3")})
				if doc.supplier_order_confirmation and frappe.db.exists("DocType", SOC3) else 0,
			"cost_changes": sum(1 for i in doc.items if abs(flt(i.new_cost) - flt(i.old_cost)) >= 0.005),
			"rate_source": doc.rate_source,
			"total_removals": sum(1 for p in doc.prices if p.action == "Delete"),
			"total_new_listings": sum(1 for p in doc.prices if p.action == "Update" and not flt(p.old_price)),
			"confirmation": doc.supplier_order_confirmation,
			"purchase_order_v3": frappe.db.get_value(SOC3, doc.supplier_order_confirmation, "purchase_order_v3")
				if doc.supplier_order_confirmation and frappe.db.exists("DocType", SOC3) else None,
			"purchase_order": doc.purchase_order,
			"buying_price_list": doc.buying_price_list,
			"supplier_currency": doc.supplier_currency,
			"company_currency": doc.company_currency,
			"conversion_rate": flt(doc.conversion_rate),
			"rounding_rule": doc.rounding_rule or "0.99",
			"effective_from": str(doc.effective_from or ""),
			"total_items": doc.total_items,
			"total_price_changes": doc.total_price_changes,
			"lines_needing_review": doc.lines_needing_review,
			"avg_cost_change_pct": flt(doc.avg_cost_change_pct),
			"avg_margin_before": flt(doc.avg_margin_before),
			"avg_margin_after": flt(doc.avg_margin_after),
			"applied_on": str(doc.applied_on or ""),
			"applied_by": doc.applied_by,
			"reverted_on": str(doc.reverted_on or ""),
			"modified": str(doc.modified),
		},
		"lists": lists,
		"rows": rows,
	}


@frappe.whitelist()
def screen_version():
	"""The grid bundle the server has now. A tab opened before an update
	compares it with the one it loaded and offers a reload."""
	from frappe.utils import get_assets_json

	return get_assets_json().get("price_grid.bundle.js")
