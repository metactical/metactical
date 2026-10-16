# Copyright (c) 2026, International Camouflage Ltd
# For license information, please see license.txt
"""Landed cost, margin and suggested-price maths for Price Revision.

Deliberately free of ``frappe`` imports so the arithmetic can be unit tested
without a site.  Everything here is pure: callers pass values in, get values
back.

Landed cost, as agreed with ICL (2026-09-17):

    landed (supplier currency) = cost * (1 + duty_rate / 100)
    landed (company currency)  = landed_supplier * conversion_rate

Freight is **not** included.  Most orders carry none, and the ones that do are
marked up heavily by hand instead.

The conversion rate is the one stamped on the Purchase Order — the rate the
goods were actually bought at — not today's rate.  It is stored on the revision
so a margin can be reproduced months later.
"""

from __future__ import annotations

# Selling lists that are not margin-bearing retail: the franchise list (other
# ICL companies buy at it) and the wholesale list.  They run thin on purpose,
# so the low-margin flag would cry wolf on every single line.
LOW_MARGIN_PRICE_LISTS = frozenset({
	"RET - CamoFRN - USD",
	"RET - GearStock - USD",
})

ROUNDING_RULES = ("0.99", "0.95", "whole", "none")


def _f(value) -> float:
	"""Frappe hands back None, '' and Decimal interchangeably."""
	if value is None or value == "":
		return 0.0
	return float(value)


def landed_cost(cost, duty_pct=0, conversion_rate=1.0):
	"""Landed cost in both the supplier's currency and the company's.

	``conversion_rate`` converts supplier currency to company currency, i.e.
	the Purchase Order's own ``conversion_rate``.  Returns a dict rather than a
	tuple — the Server Script sandbox on deverp cannot unpack sequences, and
	keeping the shapes identical across both codebases avoids surprises.
	"""
	base = _f(cost) * (1.0 + _f(duty_pct) / 100.0)
	return {
		"supplier_ccy": base,
		"company_ccy": base * (_f(conversion_rate) or 1.0),
	}


def landed_in_currency(landed, target_currency, supplier_currency, company_currency):
	"""Pick the right side of :func:`landed_cost` for a given price list.

	A price list quoted in the supplier's own currency needs no conversion at
	all — converting to CAD and back would only introduce rounding drift.
	Anything in a third currency is refused rather than guessed; the caller
	surfaces it as a line needing attention.
	"""
	if target_currency == company_currency:
		return landed["company_ccy"]
	if target_currency == supplier_currency:
		return landed["supplier_ccy"]
	return None


def margin_pct(price, landed):
	"""Gross margin as a percentage of the selling price.

	Returns ``None`` when there is no price to take a margin on, which reads
	as "unknown" on the grid rather than a misleading 0%.
	"""
	price = _f(price)
	if price <= 0:
		return None
	return (price - _f(landed)) / price * 100.0


def apply_rounding(price, rule="0.99"):
	"""Round a suggested price to the ending the banner actually uses.

	74-86% of live RET prices end in .99, so an unrounded suggestion reads as
	obviously wrong to whoever reviews it.
	"""
	price = _f(price)
	if price <= 0 or rule in (None, "", "none"):
		return price
	if rule == "whole":
		import math
		return float(math.ceil(price - 1e-9))
	if rule in ("0.99", "0.95"):
		cents = 0.99 if rule == "0.99" else 0.95
		whole = int(price)
		# Always round UP to the next ending, never to the nearest one. A
		# suggestion that rounds down hands back margin the cost increase was
		# meant to recover, and does it invisibly.
		candidate = whole + cents
		if price > candidate + 1e-9:
			candidate = whole + 1 + cents
		return round(candidate, 2)
	return price


def suggest_preserve_margin(old_price, old_landed, new_landed, rule="0.99"):
	"""Hold the existing margin percentage across a cost change.

	Needs no configuration, so it is always available even for a
	supplier/price-list pair the matrix has never seen.
	"""
	old_price = _f(old_price)
	old_landed = _f(old_landed)
	if old_price <= 0 or old_landed <= 0:
		return None
	m = (old_price - old_landed) / old_price
	if m >= 1.0:
		return None
	return apply_rounding(_f(new_landed) / (1.0 - m), rule)


def suggest_markup(new_landed, markup, rule="0.99"):
	"""Price from the markup matrix: landed cost times the learned multiplier."""
	markup = _f(markup)
	if markup <= 0:
		return None
	return apply_rounding(_f(new_landed) * markup, rule)


def build_price_line(
	*,
	price_list,
	list_currency,
	old_price,
	old_landed,
	new_landed,
	markup=None,
	rounding="0.99",
	min_margin_pct=None,
	cost_went_down=False,
	cost_change=None,
	use_suggested=True,
):
	"""Everything the grid shows for one item on one price list.

	``cost_change`` is "up", "down" or "same" (older callers pass
	``cost_went_down``). An unchanged cost always keeps today's price.

	``use_suggested`` is the revision's "Use Suggested Price" switch. On, a
	line whose cost moved takes the suggested price, up or down. Off, every
	existing price is kept and the suggestion is only shown, for a buyer to
	take cell by cell.

	The franchise and wholesale lists are exempt from the low-margin flag but
	*not* from the never-below-landed rule — the franchise price in particular
	must always sit above landed cost, since other ICL companies buy at it.
	"""
	old_margin = margin_pct(old_price, old_landed)

	if cost_change is None:
		cost_change = "down" if cost_went_down else "up"
	old = _f(old_price)

	by_matrix = suggest_markup(new_landed, markup, rounding) if markup else None
	by_hold = suggest_preserve_margin(old_price, old_landed, new_landed, rounding)
	candidates = [x for x in (by_matrix, by_hold) if x]
	if old > 0 and candidates:
		# At least today's margin, lifted to the usual markup if the item sits
		# below it. A cost rise never suggests a lower price; a cost fall
		# never suggests a higher one.
		suggested = max(candidates)
		if cost_change == "down":
			suggested = min(suggested, old)
	else:
		suggested = by_matrix or by_hold

	note = None
	if old <= 0:
		# Not on this list yet (an always-included list like the franchise
		# one, or a list added to the revision). Only the markup can price it.
		if use_suggested and by_matrix:
			proposed, action = by_matrix, "Update"
			note = "Not on this list yet; priced from the markup."
		else:
			proposed, action = 0.0, "Review"
			note = (
				"Not on this list yet; suggested {:.2f} from the markup.".format(by_matrix)
				if by_matrix else "Not on this list yet, and no markup to price it from."
			)
	elif cost_change == "same":
		proposed, action = old, "Hold"
	elif not use_suggested:
		proposed, action = old, "Hold"
		note = "Suggested prices are off; current price kept."
	elif suggested and abs(suggested - old) >= 0.005:
		proposed, action = suggested, "Update"
	elif suggested:
		proposed, action = old, "Hold"
	else:
		proposed, action = old, "Review"
		note = "No markup for this list and no current price to carry the margin from."

	# A price at or under landed cost is never a valid suggestion, on any list
	if proposed and _f(new_landed) and proposed <= _f(new_landed):
		action = "Review"
		note = "At or under landed cost ({:.2f}); needs a price.".format(_f(new_landed))

	new_margin = margin_pct(proposed, new_landed)
	exempt = price_list in LOW_MARGIN_PRICE_LISTS
	below_floor = bool(
		min_margin_pct is not None
		and not exempt
		and new_margin is not None
		and new_margin < _f(min_margin_pct)
	)
	if below_floor and action == "Hold":
		# the price isn't changing; flag the margin, don't demand a decision
		note = note or "Margin {:.1f}% is under the {:.0f}% floor; price held.".format(new_margin, _f(min_margin_pct))
	elif below_floor:
		action = "Review"
		note = note or "Margin {:.1f}% is under the {:.0f}% floor.".format(new_margin, _f(min_margin_pct))

	return {
		"price_list": price_list,
		"currency": list_currency,
		"old_price": _f(old_price),
		"old_margin_pct": old_margin,
		"suggested_by_matrix": by_matrix,
		"suggested_by_margin": by_hold,
		"suggested_price": suggested,
		"new_price": proposed,
		"new_margin_pct": new_margin,
		"margin_delta_pct": (
			None if (old_margin is None or new_margin is None) else new_margin - old_margin
		),
		"below_floor": below_floor,
		"low_margin_exempt": exempt,
		"action": action,
		"note": note,
	}
