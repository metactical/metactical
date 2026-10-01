# Copyright (c) 2026, International Camouflage Ltd
# For license information, please see license.txt
"""Prefill a Price Revision from the document that revealed the cost change."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, flt, nowdate

from metactical.icl_pricing.doctype.icl_pricing_settings.icl_pricing_settings import (
	always_price_lists,
	items_per_page,
	max_items,
)
from metactical.icl_pricing.doctype.price_revision_batch.price_revision_batch import (
	HEADER_FIELDS,
)

# Lists that exist but are not really retail banners, so they are not offered
# as default scope. They can still be added by hand.
NON_DEFAULT_SCOPE = {"RET - GorillaStoreOnly"}


def default_scope():
	"""Enabled selling lists that actually carry prices, plus the always-included ones."""
	rows = frappe.db.sql(
		"""
		SELECT pl.name
		FROM `tabPrice List` pl
		WHERE pl.selling = 1 AND pl.enabled = 1
		  AND EXISTS (SELECT 1 FROM `tabItem Price` ip WHERE ip.price_list = pl.name)
		ORDER BY pl.name
		""",
		as_dict=True,
	)
	scope = [r.name for r in rows if r.name not in NON_DEFAULT_SCOPE]
	for pl in always_price_lists():
		if pl not in scope:
			scope.append(pl)
	return scope


def set_scope(doc):
	always = set(always_price_lists())
	for pl in default_scope():
		doc.append("price_lists", {"price_list": pl, "include_all": 1 if pl in always else 0})


def supplier_price_list(supplier):
	pl = frappe.db.get_value("Supplier", supplier, "default_price_list")
	if pl:
		return pl
	guess = "SUP - {0}".format(supplier)
	return guess if frappe.db.exists("Price List", guess) else None


def finalize(header, item_rows):
	"""Persist a built selection and return the name to open in the grid.

	A selection that fits on one page becomes a single Price Revision, as
	before. A larger one is split into a batch of page revisions (each up to the
	page size); the first page is returned, so opening the result lands on it.
	The batch itself is the collective the pages belong to.
	"""
	per = items_per_page()
	cap = max_items()
	n = len(item_rows)
	if not n:
		frappe.throw(_("Nothing to revise — no items were selected."))
	if n > cap:
		frappe.throw(_("{0} items selected; the most one batch can hold is {1} "
		               "(ICL Pricing Settings). Narrow the selection down.").format(n, cap))

	if n <= per:
		doc = frappe.new_doc("Price Revision")
		doc.update({k: header[k] for k in HEADER_FIELDS if header.get(k) is not None})
		set_scope(doc)
		for it in item_rows:
			doc.append("items", it)
		doc.insert(ignore_permissions=True)
		return doc.name

	batch = frappe.new_doc("Price Revision Batch")
	batch.update({k: header[k] for k in HEADER_FIELDS if header.get(k) is not None})
	batch.items_per_page = per
	set_scope(batch)
	batch.insert(ignore_permissions=True)

	scope = [(d.price_list, d.include_all) for d in batch.price_lists]
	pages = [item_rows[i:i + per] for i in range(0, n, per)]
	first = None
	for page_no, chunk in enumerate(pages, 1):
		rev = frappe.new_doc("Price Revision")
		rev.update({k: header[k] for k in HEADER_FIELDS if header.get(k) is not None})
		rev.batch = batch.name
		rev.page_no = page_no
		for pl, include_all in scope:
			rev.append("price_lists", {"price_list": pl, "include_all": include_all})
		for it in chunk:
			rev.append("items", it)
		rev.insert(ignore_permissions=True)
		first = first or rev.name

	batch.save_roll_up()
	return first


@frappe.whitelist()
def from_purchase_order(purchase_order, include_unchanged=0):
	"""Build a draft revision from a PO whose rates differ from the cost list.

	The PO rate *is* the new cost: it is what the supplier confirmed and what
	will be invoiced. Anything matching the current cost list is left out, so a
	21-line order usually produces three or four rows rather than 21.
	"""
	po = frappe.get_doc("Purchase Order", purchase_order)
	buying_list = supplier_price_list(po.supplier)
	if not buying_list:
		frappe.throw(
			_("No supplier price list found for {0}. Set Default Price List on the "
			  "supplier first, so the revision knows which cost list to write.")
			.format(po.supplier)
		)

	header = {
		"supplier": po.supplier,
		"buying_price_list": buying_list,
		"source": "Purchase Order",
		"purchase_order": po.name,
		"company": po.company,
		"supplier_currency": po.currency,
		"conversion_rate": po.conversion_rate or 1.0,
		"rate_source": _("Purchase Order {0}").format(po.name),
		"effective_from": nowdate(),
	}

	item_rows = []
	seen = set()
	for it in po.items:
		if it.item_code in seen:
			continue
		seen.add(it.item_code)

		old_cost = flt(frappe.db.get_value(
			"Item Price",
			{"item_code": it.item_code, "price_list": buying_list},
			"price_list_rate",
		))
		new_cost = flt(it.rate)

		if not int(include_unchanged or 0) and old_cost and abs(new_cost - old_cost) < 0.005:
			continue

		item_rows.append({
			"item_code": it.item_code,
			"po3_item": it.name,
			"old_cost": old_cost,
			"new_cost": new_cost,
			"duty_pct": flt(frappe.db.get_value("Item", it.item_code, "ifw_duty_rate")),
			"supplier_currency": po.currency,
			"apply": 1,
		})

	if not item_rows:
		frappe.throw(
			_("Every line on {0} already matches {1}. Nothing to revise.")
			.format(po.name, buying_list)
		)

	return finalize(header, item_rows)


def order_lines(confirmation):
	"""Every line of the confirmation's PO3, one per item, costed.

	The ordered rate is the old cost; the supplier's confirmed rate, where
	they gave one, is the new cost. Lines they didn't confirm keep the ordered
	rate, so they show up as unchanged.
	"""
	soc = frappe.get_doc("Supplier Order Confirmation V3", confirmation)
	po3 = frappe.get_doc("Purchase Order V3", soc.purchase_order_v3)
	confirmed = {
		line.get("po3_item"): flt(line.get("confirmed_rate"))
		for line in soc.items if flt(line.get("confirmed_rate"))
	}
	duty = {}
	if frappe.get_meta("Item").has_field("ifw_duty_rate"):
		duty = dict(frappe.get_all(
			"Item", filters={"name": ("in", [r.item_code for r in po3.items] or [""])},
			fields=["name", "ifw_duty_rate"], as_list=True,
		))
	lines, seen = [], set()
	for r in po3.items:
		if not r.item_code or r.item_code in seen:
			continue
		seen.add(r.item_code)
		ordered = flt(r.rate)
		new = confirmed.get(r.name) or ordered
		lines.append({
			"item_code": r.item_code,
			"po3_item": r.name,
			"old_cost": ordered,
			"new_cost": new,
			"duty_pct": flt(duty.get(r.item_code)),
			"supplier_currency": po3.currency,
			"apply": 1,
			"changed": abs(new - ordered) >= 0.005,
		})
	return soc, po3, lines


@frappe.whitelist()
def from_confirmation(confirmation, whole_order=0):
	"""Build from a V3 Supplier Order Confirmation.

	By default only the lines whose cost changed; ``whole_order`` brings in
	the rest of the order too, for a full review.
	"""
	if not frappe.db.exists("DocType", "Supplier Order Confirmation V3"):
		frappe.throw(_("Supplier Order Confirmation V3 is not installed on this site."))

	soc, po3, lines = order_lines(confirmation)
	if not any(l["changed"] for l in lines) and not cint(whole_order):
		frappe.throw(_("{0} confirmed every line at the ordered cost.").format(soc.name))

	header = {
		"supplier": po3.supplier,
		"buying_price_list": po3.get("buying_price_list") or supplier_price_list(po3.supplier),
		"source": "Supplier Confirmation",
		"supplier_order_confirmation": soc.name,
		"whole_order": cint(whole_order),
		"purchase_order": po3.get("erp_purchase_order"),
		"company": po3.company,
		"supplier_currency": po3.currency,
		"conversion_rate": po3.conversion_rate or 1.0,
		"rate_source": _("Purchase Order V3 {0}").format(po3.name),
		"effective_from": nowdate(),
	}
	item_rows = [
		{k: v for k, v in line.items() if k != "changed"}
		for line in lines if line["changed"] or cint(whole_order)
	]
	return finalize(header, item_rows)


def set_whole_order(doc, on):
	"""Bring the rest of the order into a draft, or take it back out.

	Taking it out keeps any line whose cost has since been edited here.
	"""
	_soc, _po3, lines = order_lines(doc.supplier_order_confirmation)
	doc.whole_order = 1 if on else 0
	if on:
		have = {i.item_code for i in doc.items}
		for line in lines:
			if line["item_code"] not in have:
				doc.append("items", {k: v for k, v in line.items() if k != "changed"})
	else:
		doc.set("items", [i for i in doc.items if abs(flt(i.new_cost) - flt(i.old_cost)) >= 0.005])
		if not doc.items:
			frappe.throw(_("No line on this order has a cost change, so the whole order stays in."))


# ------------------------------------------------------------ by selection


def _tokens(search):
	import re

	return [t for t in re.split(r"[\s,;]+", (search or "").strip()) if t]


FIELDS = ("supplier", "brand", "item_group", "item_codes", "retail_skus", "template_skus", "search")


def _match(column_sql, tokens, key, values):
	"""One token matches anywhere in the column; a pasted list matches exactly."""
	if len(tokens) == 1:
		values[key] = "%{0}%".format(tokens[0])
		return column_sql.format(op="LIKE", val="%({0})s".format(key))
	values[key] = tuple(tokens)
	return column_sql.format(op="IN", val="%({0})s".format(key))


def find_items(supplier=None, brand=None, item_group=None, item_codes=None, retail_skus=None,
               template_skus=None, search=None):
	"""Item codes matching the selection, and the supplier cost lists they are on.

	Every filled-in field narrows the selection (they combine with AND):

	- ``item_codes``: item code or barcode
	- ``retail_skus``: the retail SKU (``ifw_retailskusuffix``)
	- ``template_skus``: the template (``variant_of``), by its code or its
	  retail SKU; an item with no template is its own
	- ``brand``, ``item_group`` (with its sub-groups), ``supplier``
	- ``search``: one term across code, name, retail SKU and barcode

	The code / SKU fields take one term, matched anywhere, or a pasted list
	(one per line or comma separated), matched exactly.
	"""
	conditions = ["i.disabled = 0", "i.has_variants = 0"]
	values = {}
	has_sku = frappe.get_meta("Item").has_field("ifw_retailskusuffix")
	barcode = "EXISTS (SELECT 1 FROM `tabItem Barcode` b WHERE b.parent = i.name AND b.barcode {op} {val})"

	if brand:
		conditions.append("i.brand = %(brand)s")
		values["brand"] = brand
	if item_group:
		lft, rgt = frappe.db.get_value("Item Group", item_group, ["lft", "rgt"])
		conditions.append(
			"i.item_group IN (SELECT name FROM `tabItem Group` WHERE lft >= %(lft)s AND rgt <= %(rgt)s)"
		)
		values.update(lft=lft, rgt=rgt)

	tokens = _tokens(item_codes)
	if tokens:
		conditions.append("({0} OR {1})".format(
			_match("i.item_code {op} {val}", tokens, "codes", values),
			_match(barcode, tokens, "codes", values),
		))

	tokens = _tokens(retail_skus)
	if tokens:
		if not has_sku:
			frappe.throw(_("This site's items have no retail SKU field."))
		conditions.append(_match("i.ifw_retailskusuffix {op} {val}", tokens, "skus", values))

	tokens = _tokens(template_skus)
	if tokens:
		template = "COALESCE(NULLIF(i.variant_of, ''), i.item_code)"
		parts = [_match(template + " {op} {val}", tokens, "tpl", values)]
		if has_sku:
			parts.append(_match(
				template + " IN (SELECT t.name FROM `tabItem` t WHERE t.ifw_retailskusuffix {op} {val})",
				tokens, "tpl", values,
			))
		conditions.append("(" + " OR ".join(parts) + ")")

	tokens = _tokens(search)
	if tokens:
		parts = [_match("i.item_code {op} {val}", tokens, "q", values), _match(barcode, tokens, "q", values)]
		if len(tokens) == 1:
			parts.append(_match("i.item_name {op} {val}", tokens, "q", values))
		if has_sku:
			parts.append(_match("i.ifw_retailskusuffix {op} {val}", tokens, "q", values))
		conditions.append("(" + " OR ".join(parts) + ")")

	supplier_lists = {}
	for s in frappe.get_all("Supplier", filters={"disabled": 0}, fields=["name", "default_price_list"]):
		pl = s.default_price_list or supplier_price_list(s.name)
		if pl:
			supplier_lists.setdefault(pl, s.name)
	if supplier:
		pl = supplier_price_list(supplier)
		if not pl:
			frappe.throw(_("{0} has no default price list to take costs from.").format(supplier))
		supplier_lists = {pl: supplier}
	if not supplier_lists:
		return {"by_list": {}, "suppliers": []}

	values["cost_lists"] = tuple(supplier_lists)
	rows = frappe.db.sql(
		"""
		SELECT ip.price_list, ip.item_code
		FROM `tabItem Price` ip
		JOIN `tabItem` i ON i.name = ip.item_code
		WHERE ip.price_list IN %(cost_lists)s AND ip.price_list_rate > 0 AND {0}
		GROUP BY ip.price_list, ip.item_code
		ORDER BY i.item_code
		""".format(" AND ".join(conditions)),
		values,
		as_dict=True,
	)
	by_list = {}
	for r in rows:
		by_list.setdefault(r.price_list, []).append(r.item_code)
	suppliers = sorted(
		({"supplier": supplier_lists[pl], "price_list": pl, "items": len(codes)} for pl, codes in by_list.items()),
		key=lambda x: -x["items"],
	)
	return {"by_list": by_list, "suppliers": suppliers}


def _selection(kwargs):
	return {k: kwargs.get(k) for k in FIELDS if kwargs.get(k)}


@frappe.whitelist()
def preview_selection(**kwargs):
	from metactical.pricing import jobs

	found = find_items(**_selection(kwargs))
	return {"suppliers": found["suppliers"], "limit": max_items(), "background_threshold": jobs.limits()["threshold"]}


@frappe.whitelist()
def from_selection(company=None, **kwargs):
	"""A revision for items picked by code / retail SKU / template / brand /
	supplier / item group, with no PO involved.

	Nothing has changed cost, so every existing price starts on Hold with its
	suggestion shown alongside; edit prices directly, or change a cost and the
	row reprices on save. A selection over the page size is split into a batch.
	"""
	chosen = _selection(kwargs)
	supplier = chosen.get("supplier")
	found = find_items(**chosen)
	if not found["suppliers"]:
		frappe.throw(_("No items with a supplier cost match that selection."))
	if len(found["suppliers"]) > 1 and not supplier:
		frappe.throw(_("Those items come from more than one supplier. Pick the supplier first."))
	pick = found["suppliers"][0]
	codes = found["by_list"][pick["price_list"]]

	company = company or frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
		"Global Defaults", "default_company"
	)
	company_ccy = frappe.db.get_value("Company", company, "default_currency")
	supplier_ccy = frappe.db.get_value("Price List", pick["price_list"], "currency")
	rate = 1.0
	if supplier_ccy != company_ccy:
		from erpnext.setup.utils import get_exchange_rate

		rate = flt(get_exchange_rate(supplier_ccy, company_ccy, nowdate(), "for_buying")) or 1.0

	labels = {"item_codes": _("codes"), "retail_skus": _("retail SKUs"), "template_skus": _("templates"), "search": _("search")}
	picked = ", ".join(
		"{0} {1}".format(labels[k], (v or "").replace("\n", " ")[:40]) if k in labels else v
		for k, v in chosen.items() if k != "supplier"
	)
	header = {
		"supplier": pick["supplier"],
		"buying_price_list": pick["price_list"],
		"source": "Manual",
		"company": company,
		"supplier_currency": supplier_ccy,
		"conversion_rate": rate,
		"rate_source": _("Selection: {0}").format(picked or pick["supplier"]),
		"effective_from": nowdate(),
	}
	duty_field = "ifw_duty_rate" if frappe.get_meta("Item").has_field("ifw_duty_rate") else None
	costs = dict(frappe.get_all(
		"Item Price",
		filters={"price_list": pick["price_list"], "item_code": ("in", codes)},
		fields=["item_code", "price_list_rate"],
		as_list=True,
	))
	duty = dict(frappe.get_all(
		"Item", filters={"name": ("in", codes)}, fields=["name", duty_field], as_list=True,
	)) if duty_field else {}
	item_rows = []
	for code in codes:
		cost = flt(costs.get(code))
		item_rows.append({
			"item_code": code,
			"old_cost": cost,
			"new_cost": cost,
			"duty_pct": flt(duty.get(code)),
			"supplier_currency": supplier_ccy,
			"apply": 1,
		})
	return finalize(header, item_rows)
