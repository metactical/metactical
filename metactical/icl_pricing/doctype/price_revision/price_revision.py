# Copyright (c) 2026, International Camouflage Ltd
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, now_datetime, nowdate

from metactical.icl_pricing.doctype.icl_pricing_settings.icl_pricing_settings import (
	always_price_lists,
)
from metactical.pricing.costing import build_price_line, landed_cost
from metactical.pricing.matrix import lookup_table as matrix_table


def current_prices(item_codes, price_lists):
	"""{(item_code, price_list): rate} for every pair, in a few queries."""
	out = {}
	for i in range(0, len(item_codes), 500):
		for r in frappe.get_all(
			"Item Price",
			filters={"item_code": ("in", item_codes[i:i + 500]), "price_list": ("in", price_lists)},
			fields=["item_code", "price_list", "price_list_rate"],
			order_by="modified asc",  # one price per item per list; latest wins if not
		):
			out[(r.item_code, r.price_list)] = flt(r.price_list_rate)
	return out


class PriceRevision(Document):
	def validate(self):
		self.set_currencies()
		self.recalculate()
		self.roll_up_summary()

	# The price rows are generated from the items and scoped lists, which are
	# validated themselves; checking thousands of generated rows one at a time
	# was most of the cost of saving a large revision.

	def _validate_links(self):
		with prices_set_aside(self):
			super()._validate_links()

	def _validate(self):
		with prices_set_aside(self):
			super()._validate()

	def db_insert(self, *args, **kwargs):
		super().db_insert(*args, **kwargs)
		replace_children_in_bulk(self, "prices")
		for d in self.get("prices") or []:
			d.flags.saved_in_bulk = True

	def update_child_table(self, fieldname, df=None):
		if fieldname != "prices":
			return super().update_child_table(fieldname, df)
		replace_children_in_bulk(self, fieldname)

	def on_submit(self):
		self.status = "Pending Review"

	def on_cancel(self):
		if self.status == "Applied":
			frappe.throw(
				_("{0} has already been applied. Revert it before cancelling, "
				  "so the prices it changed go back first.").format(self.name)
			)
		self.status = "Cancelled"

	# ------------------------------------------------------------------ setup

	def set_currencies(self):
		if self.buying_price_list and not self.supplier_currency:
			self.supplier_currency = frappe.db.get_value(
				"Price List", self.buying_price_list, "currency"
			)
		if self.company and not self.company_currency:
			self.company_currency = frappe.db.get_value(
				"Company", self.company, "default_currency"
			)
		if not self.conversion_rate:
			self.conversion_rate = 1.0
		if not self.effective_from:
			self.effective_from = nowdate()

	# ------------------------------------------------------- the actual maths

	def recalculate(self):
		"""Rebuild every price line from the item costs currently on the doc.

		Runs on every save so the grid can never drift from the costs above it.
		What a person decided in the grid (a typed price, a price to remove)
		is carried over; everything derived around it is recomputed.

		Everything is loaded up front, a few queries per save rather than
		several per cell, so a revision of a thousand items stays usable.
		"""
		scoped = [d.price_list for d in (self.price_lists or [])]
		if not scoped or not self.items:
			return

		include_all = {d.price_list for d in self.price_lists if d.get("include_all")}
		include_all |= set(always_price_lists())
		currency_of = dict(frappe.get_all(
			"Price List", filters={"name": ("in", scoped)}, fields=["name", "currency"], as_list=True,
		))
		codes = [i.item_code for i in self.items]
		current = current_prices(codes, scoped)
		item_meta = {
			r.name: r for r in frappe.get_all(
				"Item", filters={"name": ("in", codes)}, fields=["name", "brand", "item_group"],
			)
		}
		find_markup = matrix_table(self.buying_price_list)

		# decisions made in the grid, keyed on item + list
		decided = {}
		for p in self.prices or []:
			if p.get("edited") or p.get("remove"):
				decided[(p.item_code, p.price_list)] = {
					"price": flt(p.new_price) if p.get("edited") else 0,
					"remove": cint(p.get("remove")),
				}

		rebuilt = []
		for item in self.items:
			landed_old = landed_cost(item.old_cost, item.duty_pct, self.conversion_rate)
			landed_new = landed_cost(item.new_cost, item.duty_pct, self.conversion_rate)
			item.landed_old_cad = landed_old["company_ccy"]
			item.landed_new_cad = landed_new["company_ccy"]
			item.landed_old_usd = self._in_currency("USD", landed_old)
			item.landed_new_usd = self._in_currency("USD", landed_new)
			item.supplier_currency = self.supplier_currency
			item.cost_change_pct = (
				(flt(item.new_cost) - flt(item.old_cost)) / flt(item.old_cost) * 100.0
				if flt(item.old_cost) else 0.0
			)
			moved = flt(item.new_cost) - flt(item.old_cost)
			direction = "up" if moved >= 0.005 else "down" if moved <= -0.005 else "same"
			meta = item_meta.get(item.item_code) or {}

			for pl_name in scoped:
				ccy = currency_of.get(pl_name)
				if not ccy:
					continue
				key = (item.item_code, pl_name)
				old_price = current.get(key, 0)
				mine = decided.get(key) or {}

				# A cost change revises the prices an item already has. It only
				# prices an item new to a list when the list is always included,
				# was added to this revision for every item, or someone typed one.
				if not old_price and pl_name not in include_all and not mine.get("price"):
					continue

				old_in_ccy = self._in_currency(ccy, landed_old)
				new_in_ccy = self._in_currency(ccy, landed_new)
				if new_in_ccy is None:
					rebuilt.append(self._row(item, pl_name, ccy, {
						"old_price": old_price, "new_price": old_price, "action": "Review",
					}, note=_("{0} is in {1}; no exchange rate from {2} on file.").format(
						pl_name, ccy, self.company_currency)))
					continue
				fx_note = None
				if ccy not in (self.company_currency, self.supplier_currency):
					fx_note = _("Landed converted {0} -> {1} at {2}.").format(
						self.company_currency, ccy, flt(self._fx(ccy), 4))

				mx = find_markup(pl_name, meta.get("brand"), meta.get("item_group")) or {}
				line = build_price_line(
					price_list=pl_name,
					list_currency=ccy,
					old_price=old_price,
					old_landed=old_in_ccy,
					new_landed=new_in_ccy,
					markup=mx.get("markup"),
					rounding=mx.get("rounding_rule") or self.rounding_rule or "0.99",
					min_margin_pct=mx.get("min_margin_pct"),
					cost_change=direction,
					use_suggested=cint(self.use_suggested),
				)
				line["landed_in_list_ccy"] = new_in_ccy
				line["markup_used"] = mx.get("markup")
				line["markup_source"] = mx.get("matched_on")

				if mine.get("price"):
					take_typed_price(line, mine["price"], new_in_ccy, floor=mx.get("min_margin_pct"))
				if mine.get("remove") and old_price:
					mark_removed(line)

				rebuilt.append(self._row(item, pl_name, ccy, line, note=fx_note))

		self.set("prices", [])
		for r in rebuilt:
			self.append("prices", r)

	def _in_currency(self, currency, landed):
		"""A landed-cost pair expressed in ``currency``, or None with no rate."""
		if currency == self.supplier_currency:
			return landed["supplier_ccy"]
		if currency == self.company_currency:
			return landed["company_ccy"]
		fx = self._fx(currency)
		return landed["company_ccy"] * fx if fx else None

	def _row(self, item, price_list, currency, line, note=None):
		row = {
			"item_code": item.item_code,
			"price_list": price_list,
			"currency": currency,
			"old_price": line.get("old_price"),
			"old_margin_pct": line.get("old_margin_pct"),
			"suggested_price": line.get("suggested_price"),
			"suggested_by_matrix": line.get("suggested_by_matrix"),
			"suggested_by_margin": line.get("suggested_by_margin"),
			"markup_used": line.get("markup_used"),
			"markup_source": line.get("markup_source"),
			"new_price": line.get("new_price"),
			"edited": 1 if line.get("edited") else 0,
			"remove": 1 if line.get("remove") else 0,
			"new_margin_pct": line.get("new_margin_pct"),
			"margin_delta_pct": line.get("margin_delta_pct"),
			"landed_in_list_ccy": line.get("landed_in_list_ccy"),
			"action": line.get("action"),
			"below_floor": 1 if line.get("below_floor") else 0,
			"low_margin_exempt": 1 if line.get("low_margin_exempt") else 0,
		}
		note = " ".join(n for n in (line.get("note"), note) if n)
		if note:
			row["note"] = note
		return row

	def _fx(self, to_currency):
		"""Company currency -> ``to_currency``, cached for the recalculation."""
		cache = self.__dict__.setdefault("_fx_cache", {})
		if to_currency not in cache:
			from erpnext.setup.utils import get_exchange_rate

			cache[to_currency] = flt(get_exchange_rate(
				self.company_currency, to_currency, self.effective_from or nowdate(), "for_selling"
			))
		return cache[to_currency]

	def roll_up_summary(self):
		self.total_items = len(self.items or [])
		changes = [p for p in (self.prices or []) if p.action == "Update"]
		self.total_price_changes = len(changes)
		self.lines_needing_review = len(
			[p for p in (self.prices or []) if p.action == "Review"]
		)

		# Averages describe the cost change, so lines pulled in only for review
		# (whole order, unchanged cost) would just dilute them.
		changed = {
			i.item_code for i in (self.items or [])
			if flt(i.old_cost) and abs(flt(i.new_cost) - flt(i.old_cost)) >= 0.005
		}
		costs = [flt(i.cost_change_pct) for i in (self.items or []) if i.item_code in changed]
		self.avg_cost_change_pct = sum(costs) / len(costs) if costs else 0

		basis = [p for p in (self.prices or []) if p.item_code in changed] or list(self.prices or [])
		# like for like: prices that exist before and after (not new listings
		# or removals), so the two averages describe the same prices
		basis = [p for p in basis if p.old_margin_pct is not None and p.new_margin_pct is not None and flt(p.old_price)]
		before = [flt(p.old_margin_pct) for p in basis]
		after = [flt(p.new_margin_pct) for p in basis]
		self.avg_margin_before = sum(before) / len(before) if before else 0
		self.avg_margin_after = sum(after) / len(after) if after else 0


def replace_children_in_bulk(doc, fieldname):
	"""Save a large child table with one delete and a few bulk inserts.

	Recalculation rebuilds the price rows on every save; row-by-row inserts
	made a thousand-item revision take many seconds to save.
	"""
	child = doc.meta.get_field(fieldname).options
	frappe.db.delete(child, {"parent": doc.name, "parenttype": doc.doctype, "parentfield": fieldname})
	rows = doc.get(fieldname) or []
	if not rows:
		return
	now, user = now_datetime(), frappe.session.user
	columns, values = None, []
	for idx, d in enumerate(rows, 1):
		d.parent, d.parenttype, d.parentfield, d.idx = doc.name, doc.doctype, fieldname, idx
		d.docstatus = doc.docstatus
		if not d.name or d.get("__islocal"):
			d.name = frappe.generate_hash(length=10)
		d.creation = d.creation or now
		d.owner = d.owner or user
		d.modified, d.modified_by = now, user
		d.set("__islocal", None)
		row = d.get_valid_dict(convert_dates_to_str=True, ignore_nulls=False)
		if columns is None:
			columns = list(row.keys())
		values.append([row.get(c) for c in columns])
	insert_rows(child, columns, values)


def set_rates(pairs, now, user, chunk=500):
	"""Set many Item Price rates in a handful of statements.

	``pairs`` is [(item_price_name, rate)]. Touches ``modified`` like a normal
	save, so anything that syncs prices by modified date still sees the change.
	"""
	for i in range(0, len(pairs), chunk):
		part = pairs[i:i + chunk]
		cases = " ".join(["WHEN %s THEN %s"] * len(part))
		frappe.db.sql(
			"UPDATE `tabItem Price` SET price_list_rate = CASE name {0} END, "
			"modified = %s, modified_by = %s WHERE name IN ({1})".format(cases, ", ".join(["%s"] * len(part))),
			[v for pair in part for v in pair] + [now, user] + [n for n, _r in part],
		)


class prices_set_aside:
	"""Hide the generated price rows from Frappe's per-row checks."""

	def __init__(self, doc):
		self.doc = doc

	def __enter__(self):
		self.rows = self.doc.__dict__.get("prices")
		self.doc.__dict__["prices"] = []

	def __exit__(self, *exc):
		self.doc.__dict__["prices"] = self.rows


def insert_rows(doctype, columns, values, chunk=1000):
	"""Multi-row INSERTs. frappe.db.bulk_insert builds each statement through
	the query builder, which is slow at this size."""
	cols = ", ".join("`{0}`".format(c) for c in columns)
	one = "(" + ", ".join(["%s"] * len(columns)) + ")"
	for i in range(0, len(values), chunk):
		part = values[i:i + chunk]
		frappe.db.sql(
			"INSERT INTO `tab{0}` ({1}) VALUES {2}".format(doctype, cols, ", ".join([one] * len(part))),
			[v for row in part for v in row],
		)


def take_typed_price(line, price, landed, floor=None):
	"""Overlay a price someone typed onto a freshly calculated line.

	Typing a price *is* the decision, so it clears Review, with one exception:
	a price at or under landed cost is never written, on any list.
	"""
	price = flt(price)
	old = flt(line.get("old_price"))
	line["new_price"] = price
	line["edited"] = 1
	line["new_margin_pct"] = (price - flt(landed)) / price * 100.0 if price else None
	line["margin_delta_pct"] = (
		None if line.get("old_margin_pct") is None or line["new_margin_pct"] is None
		else line["new_margin_pct"] - flt(line["old_margin_pct"])
	)
	line["below_floor"] = bool(
		floor and not line.get("low_margin_exempt")
		and line["new_margin_pct"] is not None and line["new_margin_pct"] < flt(floor)
	)

	if flt(landed) and price <= flt(landed):
		line["action"] = "Review"
		line["note"] = _("Set by hand at or under landed cost ({0}).").format(flt(landed, 2))
	elif abs(price - old) < 0.005:
		line["action"] = "Hold"
		line["note"] = _("Set by hand: keep the current price.")
	else:
		line["action"] = "Update"
		line["note"] = _("Set by hand.") + (
			" " + _("Under the {0}% floor.").format(flt(floor, 0)) if line["below_floor"] else ""
		)


def mark_removed(line):
	line["action"] = "Delete"
	line["remove"] = 1
	line["new_price"] = 0
	line["new_margin_pct"] = None
	line["margin_delta_pct"] = None
	line["below_floor"] = False
	line["note"] = _("This price will be removed from the list.")


# --------------------------------------------------------------------- apply


@frappe.whitelist()
def apply_revision(name, progress=None):
	"""Write the supplier cost and every accepted selling price to Item Price.

	Every write is logged with its previous value, which is what makes
	:func:`revert_revision` possible — ICL keeps one Item Price per item per
	list and has no price history otherwise, so the log *is* the history.

	Works in batches: each batch is written, logged and committed before the
	next, with a pause between them when running as a background job. A run
	that stops part way can simply be run again; prices already at their new
	rate are skipped.
	"""
	from metactical.pricing import jobs

	doc = frappe.get_doc("Price Revision", name)
	if doc.docstatus != 1:
		frappe.throw(_("Submit the revision before applying it."))
	if doc.status == "Applied":
		frappe.throw(_("{0} has already been applied.").format(name))

	work = [("cost", i) for i in doc.items if i.apply]
	work += [("price", p) for p in doc.prices if p.action in ("Update", "Delete")]
	size = jobs.limits()["batch"]
	written = removed = 0

	for start in range(0, len(work), size):
		chunk = work[start:start + size]
		w = PriceWriter(doc.name, [
			(x.item_code, doc.buying_price_list if kind == "cost" else x.price_list) for kind, x in chunk
		])
		for kind, x in chunk:
			if kind == "cost":
				written += w.write(x.item_code, doc.buying_price_list, doc.supplier_currency,
				                   flt(x.new_cost), buying=True)
			elif x.action == "Update":
				written += w.write(x.item_code, x.price_list, x.currency, flt(x.new_price))
			else:
				removed += w.delete(x.item_code, x.price_list)
		w.flush()
		frappe.db.commit()
		if progress:
			done = min(start + size, len(work))
			progress.update(done, len(work), _("Writing prices: {0} of {1}").format(done, len(work)))
			jobs.pause()

	doc.db_set("status", "Applied")
	doc.db_set("applied_on", now_datetime())
	doc.db_set("applied_by", frappe.session.user)
	frappe.db.commit()
	return {"written": written, "removed": removed, "status": "Applied"}


class PriceWriter:
	"""Writes Item Prices for one revision and logs each change.

	Existing prices are read once up front and log rows go in as one bulk
	insert, so applying thousands of prices takes seconds, not minutes.
	"""

	LOG_FIELDS = ["name", "creation", "modified", "owner", "modified_by", "docstatus", "idx",
	              "price_revision", "item_code", "price_list", "currency", "old_rate", "new_rate",
	              "item_price", "action", "changed_on", "changed_by", "reverted"]

	def __init__(self, revision, pairs):
		self.revision = revision
		self.now = now_datetime()
		self.user = frappe.session.user
		self.logs = []
		self.updates = []
		self.existing = {}
		codes = sorted({c for c, _pl in pairs})
		lists = sorted({pl for _c, pl in pairs})
		for i in range(0, len(codes), 500):
			for r in frappe.get_all(
				"Item Price",
				filters={"item_code": ("in", codes[i:i + 500]), "price_list": ("in", lists or [""])},
				fields=["name", "item_code", "price_list", "price_list_rate", "currency"],
				order_by="modified asc",
			):
				self.existing[(r.item_code, r.price_list)] = r

	def write(self, item_code, price_list, currency, rate, buying=False):
		if not rate:
			return 0
		ex = self.existing.get((item_code, price_list))
		if ex:
			if flt(ex.price_list_rate) == flt(rate):
				return 0
			self.updates.append((ex.name, flt(rate)))
			self._log(item_code, price_list, currency, ex.price_list_rate, rate, ex.name, "Applied")
		else:
			ip = frappe.get_doc({
				"doctype": "Item Price",
				"item_code": item_code,
				"price_list": price_list,
				"price_list_rate": rate,
				"currency": currency,
				"buying": 1 if buying else 0,
				"selling": 0 if buying else 1,
			}).insert(ignore_permissions=True)
			self._log(item_code, price_list, currency, 0, rate, ip.name, "Created")
		return 1

	def delete(self, item_code, price_list):
		ex = self.existing.get((item_code, price_list))
		if not ex:
			return 0
		self._log(item_code, price_list, ex.currency, ex.price_list_rate, 0, ex.name, "Deleted")
		frappe.delete_doc("Item Price", ex.name, ignore_permissions=True, force=True)
		return 1

	def _log(self, item_code, price_list, currency, old, new, item_price, action):
		self.logs.append([
			frappe.generate_hash(length=12), self.now, self.now, self.user, self.user, 0, 0,
			self.revision, item_code, price_list, currency, flt(old), flt(new),
			item_price, action, self.now, self.user, 0,
		])

	def flush(self):
		set_rates(self.updates, self.now, self.user)
		self.updates = []
		if self.logs:
			insert_rows("Price Revision Log", self.LOG_FIELDS, self.logs)
			self.logs = []


@frappe.whitelist()
def revert_revision(name, progress=None):
	"""Put every price this revision touched back to what it was.

	Changed prices get their old rate back, removed prices are recreated, and
	prices the revision created are removed again, so a revert is a true undo.
	Batched like :func:`apply_revision`; each log row is marked reverted with
	its batch, so a revert that stops part way picks up where it left off.
	It also undoes a partial apply (one that stopped before finishing).
	"""
	from metactical.pricing import jobs

	doc = frappe.get_doc("Price Revision", name)
	logs = frappe.get_all(
		"Price Revision Log",
		filters={"price_revision": name, "reverted": 0},
		fields=["name", "item_price", "old_rate", "action", "item_code", "price_list", "currency"],
		order_by="changed_on asc",
	)
	if doc.status != "Applied" and not logs:
		frappe.throw(_("Only an applied revision can be reverted."))

	flags = {r.name: r for r in frappe.get_all("Price List", fields=["name", "buying", "selling"])}
	size = jobs.limits()["batch"]
	reverted = 0

	for start in range(0, len(logs), size):
		chunk = logs[start:start + size]
		alive = set(frappe.get_all(
			"Item Price", filters={"name": ("in", [l.item_price for l in chunk if l.item_price] or [""])}, pluck="name",
		))
		restore = []
		for log in chunk:
			if log.action == "Applied" and log.item_price in alive:
				restore.append((log.item_price, flt(log.old_rate)))
				reverted += 1
			elif log.action == "Created" and log.item_price in alive:
				# ours to begin with, so no deleted-document record is needed
				frappe.db.delete("Item Price", {"name": log.item_price})
				reverted += 1
			elif log.action == "Deleted" and not frappe.db.exists(
				"Item Price", {"item_code": log.item_code, "price_list": log.price_list}
			):
				pl = flags.get(log.price_list) or {}
				frappe.get_doc({
					"doctype": "Item Price",
					"item_code": log.item_code,
					"price_list": log.price_list,
					"currency": log.currency,
					"price_list_rate": log.old_rate,
					"buying": pl.get("buying"),
					"selling": pl.get("selling"),
				}).insert(ignore_permissions=True)
				reverted += 1
		set_rates(restore, now_datetime(), frappe.session.user)
		frappe.db.sql(
			"UPDATE `tabPrice Revision Log` SET reverted = 1 WHERE name IN %(names)s",
			{"names": tuple(l.name for l in chunk)},
		)
		frappe.db.commit()
		if progress:
			done = min(start + size, len(logs))
			progress.update(done, len(logs), _("Putting prices back: {0} of {1}").format(done, len(logs)))
			jobs.pause()

	doc.db_set("status", "Reverted")
	doc.db_set("reverted_on", now_datetime())
	doc.db_set("reverted_by", frappe.session.user)
	frappe.db.commit()
	return {"reverted": reverted, "left_in_place": len(logs) - reverted, "status": "Reverted"}


@frappe.whitelist()
def outstanding_for_purchase_order(purchase_order):
	"""Revisions still unapplied against a PO — the receiving gate reads this."""
	return frappe.get_all(
		"Price Revision",
		filters={
			"purchase_order": purchase_order,
			"status": ("in", ["Draft", "Pending Review"]),
			"docstatus": ("<", 2),
		},
		fields=["name", "status", "total_price_changes", "avg_cost_change_pct"],
	)
