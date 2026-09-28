# Copyright (c) 2026, International Camouflage Ltd
# For license information, please see license.txt
"""Markup matrix: what ICL already charges, learned from its own price history.

Markup is not one house rule. It varies by supplier *and* by banner, and the
spread within each pair is tight enough to be a rule rather than noise:

    supplier               RET - Camo   RET - GPD   RET - CamoUSA
    5.11 Tactical               2.69        1.76          1.78
    Condor Outdoor              3.42        2.21          1.67
    Rothco                      3.23        2.09          2.28

So the matrix is *derived*, not typed in. :func:`rebuild_from_history` reads
live Item Price rows, takes the median ratio per pair, and records the sample
size and quartiles alongside it so a reviewer can see how much to trust a row.

The ratio is retail price over **landed** cost in the retail list's currency:
cost x (1 + duty) x the exchange rate. That is exactly the basis a revision
multiplies it by. Learning it over raw supplier cost instead counted the
USD -> CAD rate twice on every cross-currency pair.

The median is used rather than the mean because a handful of clearance items
priced below cost, and the odd 40x outlier, drag an average badly.
"""

from __future__ import annotations

import frappe
from frappe.utils import flt, nowdate

# Ratios outside this band are data errors, not pricing decisions: below 1.0 is
# selling under cost, and above 12 is almost always a stale or wrong cost.
MIN_SANE_RATIO = 1.0
MAX_SANE_RATIO = 12.0

# Below this many observations a median means very little. The row is still
# written, so the gap is visible, but it is marked low confidence.
MIN_CONFIDENT_SAMPLE = 30


def _selling_lists():
	return frappe.get_all(
		"Price List",
		filters={"selling": 1, "enabled": 1},
		pluck="name",
	)


@frappe.whitelist()
def rebuild_from_history(supplier_price_list=None, commit_every=50):
	"""Recompute every markup from live Item Price data.

	Safe to re-run: rows are upserted on (buying_price_list, selling_price_list).
	Pass ``supplier_price_list`` to refresh a single supplier rather than all.

	Returns a summary dict — no tuples, so the same shape works if this is ever
	ported into a Server Script.
	"""
	frappe.only_for(("System Manager", "Purchase Manager"))
	where = ""
	params = {"lo": MIN_SANE_RATIO, "hi": MAX_SANE_RATIO}
	if supplier_price_list:
		where = "AND sup.price_list = %(splist)s"
		params["splist"] = supplier_price_list

	fx_sql = _fx_case(params)
	duty_sql = (
		"(1 + IFNULL(it.ifw_duty_rate, 0) / 100)"
		if frappe.get_meta("Item").has_field("ifw_duty_rate") else "1"
	)
	landed = "(sup.price_list_rate * {0} * {1})".format(duty_sql, fx_sql)

	rows = frappe.db.sql(
		"""
		SELECT supplier_list, retail_list, cnt,
		       AVG(ratio)  AS median_markup,
		       MIN(ratio)  AS lo_mid,
		       MAX(ratio)  AS hi_mid
		FROM (
			SELECT sup.price_list AS supplier_list,
			       ret.price_list AS retail_list,
			       ret.price_list_rate / {landed} AS ratio,
			       ROW_NUMBER() OVER (
			           PARTITION BY sup.price_list, ret.price_list
			           ORDER BY ret.price_list_rate / {landed}
			       ) AS rn,
			       COUNT(*) OVER (
			           PARTITION BY sup.price_list, ret.price_list
			       ) AS cnt
			FROM `tabItem Price` sup
			JOIN `tabItem Price` ret ON ret.item_code = sup.item_code
			JOIN `tabItem` it ON it.name = sup.item_code
			JOIN `tabPrice List` bl ON bl.name = sup.price_list AND bl.buying = 1
			JOIN `tabPrice List` sl ON sl.name = ret.price_list
			                       AND sl.selling = 1 AND sl.enabled = 1
			WHERE sup.price_list_rate > 0
			  AND ret.price_list_rate > 0
			  -- RET - CamoFRN - USD is flagged buying as well as selling, because
			  -- franchisee companies buy at it. That is legitimate as a cost base,
			  -- but a list against itself is always 1.0x and means nothing.
			  AND sup.price_list <> ret.price_list
			  AND ret.price_list_rate / {landed} BETWEEN %(lo)s AND %(hi)s
			  {where}
		) t
		WHERE rn IN (FLOOR((cnt + 1) / 2), CEILING((cnt + 1) / 2))
		GROUP BY supplier_list, retail_list, cnt
		""".format(landed=landed, where=where),
		params,
		as_dict=True,
	)

	written = 0
	for i, r in enumerate(rows):
		_upsert(
			buying_price_list=r.supplier_list,
			selling_price_list=r.retail_list,
			markup=round(float(r.median_markup or 0), 4),
			sample_size=int(r.cnt or 0),
			spread_low=round(float(r.lo_mid or 0), 4),
			spread_high=round(float(r.hi_mid or 0), 4),
		)
		written += 1
		if commit_every and i and i % commit_every == 0:
			frappe.db.commit()

	frappe.db.commit()
	return {
		"pairs_written": written,
		"as_of": nowdate(),
		"scope": supplier_price_list or "all suppliers",
	}


def _fx_case(params):
	"""SQL for "1 of the supplier list's currency in the retail list's", today.

	Only a handful of currency pairs exist, so the rates go in as a CASE
	rather than a join. Historic prices are converted at today's rate, which
	is the best available; a revision converts at the PO's own rate.
	"""
	from erpnext.setup.utils import get_exchange_rate

	currencies = sorted({
		c for c in frappe.get_all("Price List", filters={"enabled": 1}, pluck="currency") if c
	})
	parts = []
	for i, a in enumerate(currencies):
		for b in currencies:
			if a == b:
				continue
			rate = flt(get_exchange_rate(a, b, nowdate(), "for_selling"))
			if not rate:
				continue
			key = "fx_{0}_{1}".format(a, b).lower()
			params[key] = rate
			params[key + "_from"], params[key + "_to"] = a, b
			parts.append("WHEN bl.currency = %({0}_from)s AND sl.currency = %({0}_to)s THEN %({0})s".format(key))
	if not parts:
		return "1"
	return "(CASE WHEN bl.currency = sl.currency THEN 1 {0} ELSE NULL END)".format(" ".join(parts))


def _upsert(**kw):
	name = frappe.db.get_value(
		"Pricing Matrix",
		{
			"buying_price_list": kw["buying_price_list"],
			"selling_price_list": kw["selling_price_list"],
			"item_group": ("is", "not set"),
			"brand": ("is", "not set"),
		},
		"name",
	)
	payload = dict(kw)
	payload["derived_on"] = nowdate()
	payload["derived_from_history"] = 1
	payload["low_confidence"] = 1 if kw["sample_size"] < MIN_CONFIDENT_SAMPLE else 0

	if name:
		doc = frappe.get_doc("Pricing Matrix", name)
		# never clobber a markup a human has pinned
		if doc.locked:
			return
		doc.update(payload)
		doc.save(ignore_permissions=True)
	else:
		doc = frappe.get_doc(dict(doctype="Pricing Matrix", **payload))
		doc.insert(ignore_permissions=True)


def lookup(buying_price_list, selling_price_list, item_code=None):
	"""Most specific markup wins: item group + brand, then brand, then the pair.

	Returns a dict with the markup and where it came from, so the UI can show
	*why* a suggestion is what it is rather than producing a bare number.
	"""
	brand = item_group = None
	if item_code:
		meta = frappe.db.get_value("Item", item_code, ["brand", "item_group"], as_dict=True)
		if meta:
			brand, item_group = meta.brand, meta.item_group

	for filters, source in (
		({"brand": brand, "item_group": item_group}, "brand + item group"),
		({"brand": brand, "item_group": ("is", "not set")}, "brand"),
		({"brand": ("is", "not set"), "item_group": item_group}, "item group"),
		({"brand": ("is", "not set"), "item_group": ("is", "not set")}, "supplier list"),
	):
		if "brand" in filters and filters["brand"] is None:
			continue
		if "item_group" in filters and filters["item_group"] is None:
			continue
		f = dict(filters)
		f["buying_price_list"] = buying_price_list
		f["selling_price_list"] = selling_price_list
		f["disabled"] = 0
		row = frappe.db.get_value(
			"Pricing Matrix", f,
			["name", "markup", "min_margin_pct", "rounding_rule", "sample_size", "low_confidence"],
			as_dict=True,
		)
		if row and row.markup:
			row["matched_on"] = source
			return row

	return None


def lookup_table(buying_price_list):
	"""Same precedence as :func:`lookup`, from one query for the whole revision.

	Returns ``find(selling_price_list, brand, item_group)``. A revision of a
	thousand items across ten lists would otherwise run tens of thousands of
	lookups on every save.
	"""
	rows = frappe.get_all(
		"Pricing Matrix",
		filters={"buying_price_list": buying_price_list, "disabled": 0},
		fields=["name", "selling_price_list", "brand", "item_group", "markup",
		        "min_margin_pct", "rounding_rule", "sample_size", "low_confidence"],
	)
	index = {
		(r.selling_price_list, r.brand or None, r.item_group or None): r
		for r in rows if r.markup
	}
	fallback = {}  # selling list -> median of every supplier's markup, filled lazily

	def across_suppliers(selling_price_list):
		if selling_price_list not in fallback:
			vals = sorted(
				flt(m) for m in frappe.get_all(
					"Pricing Matrix",
					filters={"selling_price_list": selling_price_list, "disabled": 0,
					         "brand": ("is", "not set"), "item_group": ("is", "not set"),
					         "low_confidence": 0},
					pluck="markup",
				) if flt(m)
			)
			med = None
			if vals:
				mid = len(vals) // 2
				med = vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2
			fallback[selling_price_list] = med
		return fallback[selling_price_list]

	def find(selling_price_list, brand=None, item_group=None):
		brand, item_group = brand or None, item_group or None
		tries = []
		if brand and item_group:
			tries.append(((brand, item_group), "brand + item group"))
		if brand:
			tries.append(((brand, None), "brand"))
		if item_group:
			tries.append(((None, item_group), "item group"))
		tries.append(((None, None), "supplier list"))
		for (b, g), source in tries:
			row = index.get((selling_price_list, b, g))
			if row:
				out = dict(row)
				out["matched_on"] = source
				return out
		# no history for this supplier on this list (e.g. a supplier new to
		# the franchise list): what ICL charges across its other suppliers
		med = across_suppliers(selling_price_list)
		if med:
			return {"markup": med, "matched_on": "all suppliers (median)", "low_confidence": 1}
		return None

	return find
