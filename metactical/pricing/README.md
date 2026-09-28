# Price Revision

When a supplier confirms an order at a different cost, the cost change is
currently recorded and then goes nowhere. `Supplier Order Confirmation V3 Item`
has carried `confirmed_rate` and `rate_variance_pct` since the V3 build, and
**nothing in the system reads them**. No script anywhere writes `Item Price`.

The consequence is the problem ICL actually reports: goods are received at a
cost 20% higher than the order, retail never moves, and the margin erosion is
invisible until someone happens to look.

This module closes that loop.

---

## Decisions (ICL, 2026-09-17)

| Question | Answer |
|---|---|
| Landed cost | `cost × (1 + duty_rate/100) × conversion_rate`. **No freight** — most orders have none, and the ones that do are marked up by hand. |
| Which FX rate | The Purchase Order's own `conversion_rate` — what the goods were actually bought at. Stamped on the revision so a margin can be reproduced later. |
| Cost goes down | **Hold** the retail price and take the margin. The suggestion is still shown, so a buyer can take it deliberately. |
| Scope | Items on the PO only. Catalogue-wide repricing is a later, separate screen. |
| RET - Camo vs Gorilla | Separate banners, separately priced. Never grouped. |
| Margin floor | Flag, don't block. Exempt: the franchise and wholesale lists, which run thin by design. |
| Downstream | `Item Price` is the source of truth. Nothing else to push. |

## Landed cost

```
landed (supplier ccy) = cost × (1 + duty_rate / 100)
landed (company ccy)  = landed (supplier ccy) × conversion_rate
```

A price list quoted in the **supplier's own** currency (RET - CamoUSA against a
USD supplier) uses the supplier-currency figure directly rather than converting
to CAD and back — the round trip only adds rounding drift. A list in a third
currency is refused rather than guessed, and surfaces as a line needing
attention.

The grid always shows landed cost in CAD as well, whatever the list currency.

## Suggested prices

Two models, both shown side by side so the buyer can see the difference:

**Preserve margin** — `old_price × (new_landed / old_landed)`. Holds the
existing percentage exactly. No configuration, always available.

**Markup matrix** — `landed × markup`, where the markup is *derived from ICL's
own price history* rather than typed in. See `matrix.py`.

Both are then rounded to the banner's ending. **Rounding is always up, never to
nearest**: 74–86% of live RET prices end in `.99`, and a suggestion that rounds
down quietly hands back the margin the cost increase was meant to recover.

## Why the matrix is derived

Markup varies by supplier *and* banner, and is tight enough within each pair to
be a rule:

| supplier | RET - Camo | RET - GPD | RET - CamoUSA |
|---|---|---|---|
| 5.11 Tactical | 2.69 | 1.76 | 1.78 |
| Condor Outdoor | 3.42 | 2.21 | 1.67 |
| Rothco | 3.23 | 2.09 | 2.28 |

`rebuild_from_history()` reads live `Item Price` rows and takes the **median**
ratio per pair — the mean is dragged badly by clearance items priced under cost
and the occasional 40× outlier. It records the sample size and the middle
spread next to each markup, and marks anything under 30 observations as low
confidence, so a reviewer can tell a rule from a guess.

Ratios outside 1.0–12.0 are excluded as data errors rather than pricing
decisions. A markup a human has pinned (`locked`) is never overwritten.

Lookup resolves most-specific-first: brand + item group, then brand, then item
group, then the supplier/banner pair. The match reason is returned so the UI can
show *why* a suggestion is what it is.

## Never below landed

The franchise list (`RET - CamoFRN - USD`) and the wholesale list
(`RET - GearStock - USD`) are exempt from the low-margin flag — they run thin on
purpose. They are **not** exempt from the rule that a price may never sit at or
below landed cost. The franchise list in particular is what other ICL companies
buy at, so it must always clear cost.

## Tests

```
python -m unittest discover -s apps/metactical/metactical/pricing/tests -t . -p "test_*.py"
```

29 tests, no site required — `costing.py` imports nothing from frappe on
purpose, so the arithmetic can be checked in isolation.

## Status

Built here:

- `costing.py` — landed cost, margins, suggestions, rounding, floor rules
- `matrix.py` — derive markups from history, most-specific lookup
- `tests/` — 29 unit tests over the maths

Still to come, in order:

1. DocTypes — `Price Revision`, its two child tables, `Pricing Matrix`,
   `Price Revision Log`
2. Frappe page + Vue UI
3. Apply / revert against `Item Price`, with every change logged so a revision
   can be rolled back
4. Gate: block receiving while a revision is outstanding, and post it to
   Rocket.Chat for review
