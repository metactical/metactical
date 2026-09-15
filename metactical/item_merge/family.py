"""Reads and writes on one template family: find templates, merge templates, create attribute
variants, line old variants up with new ones.

Everything runs in-process through the document API (get_doc / save / rename_doc / insert), so
validation, the CustomItem rename hooks, Item Merge History and the website webhooks fire exactly
as they do when someone does the same thing in the Item form.
"""
import re
from collections import Counter

import frappe

from metactical.item_merge import rules
from metactical.item_merge.pairing import VARIANT_NUMBER, plan_pairs
from metactical.item_merge.rules import UserError

ITEM_FIELDS = ["name", "item_name", "ifw_retailskusuffix", "variant_of", "is_stock_item", "stock_uom",
			   "has_batch_no", "has_serial_no", "is_fixed_asset", "disabled", "item_group", "brand"]
TEMPLATE_ATTRIBUTE_KEYS = ("attribute", "from_range", "to_range", "increment", "numeric_values")
SEARCH_LIMIT = 60


# ---------- loaders: one query per concern, not one per item ----------

def exists(code):
	return bool(code) and bool(frappe.db.exists("Item", code))


def load_items(codes):
	"""Item rows shaped for pairing and preflight: the fields above plus their attributes."""
	codes = list(dict.fromkeys(codes or []))
	if not codes:
		return {}
	docs = {r.name: {**r, "attributes": []} for r in
			frappe.get_all("Item", filters={"name": ["in", codes]}, fields=ITEM_FIELDS)}
	for r in frappe.get_all("Item Variant Attribute", filters={"parent": ["in", codes], "parenttype": "Item"},
							fields=["parent", "attribute", "attribute_value"], order_by="idx asc"):
		if r.attribute and r.parent in docs:
			docs[r.parent]["attributes"].append({"attribute": r.attribute, "attribute_value": r.attribute_value})
	return docs


def load_stock(codes):
	codes = list(dict.fromkeys(codes or []))
	stock = {c: {"qty": 0.0, "bins": 0, "ledger": 0} for c in codes}
	if not codes:
		return stock
	for r in frappe.get_all("Bin", filters={"item_code": ["in", codes]},
							fields=["item_code", "sum(actual_qty) as qty", "count(name) as bins"], group_by="item_code"):
		stock[r.item_code].update(qty=r.qty or 0, bins=r.bins)
	for r in frappe.get_all("Stock Ledger Entry", filters={"item_code": ["in", codes], "is_cancelled": 0},
							fields=["item_code", "count(name) as n"], group_by="item_code"):
		stock[r.item_code]["ledger"] = r.n
	return stock


def variant_codes(template):
	return frappe.get_all("Item", filters={"variant_of": template}, order_by="name asc", pluck="name")


def load_template(template):
	if not exists(template):
		raise UserError(f"Template {template} does not exist")
	tdoc = frappe.get_doc("Item", template).as_dict()
	if not tdoc.get("has_variants"):
		raise UserError(f"{template} is not a template (Has Variants is off)")
	return tdoc


def load_family(template):
	tdoc = load_template(template)
	codes = variant_codes(template)
	docs = load_items(codes)
	return tdoc, [docs[c] for c in codes if c in docs], load_stock(codes)


def is_new(doc):
	return any(a["attribute"] != VARIANT_NUMBER and a.get("attribute_value") for a in doc.get("attributes") or [])


def variant_view(doc, stock):
	s = stock.get(doc["name"], {})
	return {
		"item_code": doc["name"],
		"item_name": doc.get("item_name"),
		"retail_sku": doc.get("ifw_retailskusuffix"),
		"is_new": is_new(doc),
		"attributes": {a["attribute"]: a.get("attribute_value") for a in doc.get("attributes") or []},
		"qty": s.get("qty", 0),
		"ledger_count": s.get("ledger", 0),
		"stock_uom": doc.get("stock_uom"),
		"is_stock_item": bool(doc.get("is_stock_item")),
		"has_batch_no": bool(doc.get("has_batch_no")),
		"has_serial_no": bool(doc.get("has_serial_no")),
		"is_fixed_asset": bool(doc.get("is_fixed_asset")),
		"disabled": bool(doc.get("disabled")),
		"item_group": doc.get("item_group"),
	}


def add_activity(item_code, message):
	"""Writes made outside a job (templates and variants steps) leave a line on the Item's timeline."""
	try:
		frappe.get_doc("Item", item_code).add_comment("Info", f"Item Merge: {message}")
	except Exception:
		frappe.log_error(title="Item Merge activity comment", message=frappe.get_traceback())


# ---------- templates stuck in a group item group ----------
# ERPNext refuses to save an item whose item_group is a group ("Item Group 01 - Products is a
# group"). Thousands of templates sit in "01 - Products", so any save of such a template - adding
# attributes, Maintain Stock, dropping Variant Number - fails until the group is fixed.

def group_flags(groups):
	groups = sorted({g for g in groups if g})
	if not groups:
		return {}
	return {r.name: bool(r.is_group) for r in
			frappe.get_all("Item Group", filters={"name": ["in", groups]}, fields=["name", "is_group"])}


def template_group_fix(tdoc):
	"""{} if the template's item group is fine, else {"item_group": <the one group its variants use>}."""
	g = tdoc.get("item_group")
	if not g or not group_flags([g]).get(g):
		return {}
	kids = frappe.get_all("Item", filters={"variant_of": tdoc.get("name")}, pluck="item_group")
	kid_flags = group_flags(kids)
	leaf = sorted({k for k in kids if k and not kid_flags.get(k)})
	if len(leaf) == 1:
		return {"item_group": leaf[0]}
	raise UserError(f"{tdoc.get('name')} is in item group '{g}', which is a group, so ERPNext won't save it. "
					+ (f"Its variants use several groups ({', '.join(leaf)})" if leaf else "Its variants don't have one either")
					+ " - set the template's Item Group, then try again.")


def update_template(template, updates, log=None):
	"""Save a template, fixing a group item_group on the way (logged)."""
	log = log or (lambda m: None)
	doc = frappe.get_doc("Item", template)
	fix = template_group_fix(doc.as_dict())
	if fix:
		log(f"template {template}: item_group is a group - set to {fix['item_group']}, the group its variants use")
	for field, value in {**fix, **updates}.items():
		doc.set(field, value)
	doc.save()
	return fix


def template_attribute_rows(tdoc, drop=None):
	return [{k: a.get(k) for k in TEMPLATE_ATTRIBUTE_KEYS if a.get(k) is not None}
			for a in tdoc.get("attributes") or [] if a.get("attribute") != drop]


# ---------- step 1: find and merge templates ----------

def search_templates(sku=None, name=None, limit=SEARCH_LIMIT):
	"""Templates by part of the SKU and/or the item name. Every word of the name must appear,
	in any order ("fleece vest" finds "Spec Ops Tactical Fleece Vest")."""
	sku = (sku or "").strip()
	words = [w for w in (name or "").split() if w]
	if len(sku) < 2 and len("".join(words)) < 2:
		raise UserError("Type at least 2 characters of the template SKU or name")
	filters = [["has_variants", "=", 1]]
	if sku:
		filters.append(["name", "like", f"%{sku}%"])
	filters += [["item_name", "like", f"%{w}%"] for w in words]
	rows = frappe.get_list("Item", filters=filters, fields=["name", "item_name", "disabled", "item_group", "brand"],
						   order_by="name asc", limit_page_length=limit)
	counts = variant_counts([r.name for r in rows])
	return [{"item_code": r.name, "item_name": r.item_name, "item_group": r.item_group, "brand": r.brand,
			 "disabled": bool(r.disabled), "variant_count": counts.get(r.name, 0)} for r in rows]


def variant_counts(templates):
	if not templates:
		return {}
	return {r.variant_of: r.n for r in frappe.get_all("Item", filters={"variant_of": ["in", list(templates)]},
													  fields=["variant_of", "count(name) as n"], group_by="variant_of")}


def rename_template(template, new_code=None, item_name=None, log=None):
	"""Change a template's item code and/or item name.

	Code: rename_doc updates every Link, including each variant's variant_of; that is checked
	afterwards. Variant codes themselves don't change. Name: a normal save of the template (its
	variants keep their own names)."""
	log = log or (lambda m: None)
	new_code = (new_code or "").strip() or template
	item_name = (item_name or "").strip() or None
	tdoc = load_template(template)
	rename = new_code != template
	rename_name = bool(item_name) and item_name != (tdoc.get("item_name") or "")
	if not rename and not rename_name:
		raise UserError("Nothing to change: type a new template code or item name")
	kids = variant_codes(template)
	if rename:
		rules.check_code(new_code)
		if exists(new_code):
			if new_code in kids:
				raise UserError(f"{new_code} is still an old variant under this template. Its code frees up once it is "
								f"merged away - rename the template after the merge, on the Item codes screen.")
			raise UserError(f"{new_code} already exists as an item")
		frappe.rename_doc("Item", template, new_code)
		if exists(template) or not exists(new_code):
			raise UserError(f"Renaming {template} to {new_code} did not take effect")
		moved = variant_codes(new_code)
		if len(moved) != len(kids):
			raise UserError(f"{new_code} now has {len(moved)} variant(s), expected {len(kids)} - check the template")
		log(f"template {template} renamed to {new_code} ({len(kids)} variant(s) follow)")
	if rename_name:
		update_template(new_code, {"item_name": item_name}, log)
		log(f"template {new_code}: item name '{tdoc.get('item_name')}' -> '{item_name}'")
	return {"template": new_code, "renamed_from": template if rename else None, "variants": len(kids),
			"item_name": item_name if rename_name else tdoc.get("item_name")}


def consolidation_check(target, sources):
	"""Before merging templates: do they look like one product, and can the result be saved?"""
	codes = [c for c in dict.fromkeys([target, *(sources or [])]) if c]
	tdocs = {r.name: r for r in frappe.get_all("Item", filters={"name": ["in", codes]}, fields=["name", "item_name", "item_group"])}
	kids = frappe.get_all("Item", filters={"variant_of": ["in", codes]}, fields=["name", "variant_of", "item_group"])
	flags = group_flags([k.item_group for k in kids] + [t.item_group for t in tdocs.values()])
	rows = []
	for c in codes:
		t = tdocs.get(c) or {}
		mine = [k for k in kids if k.variant_of == c]
		counts = Counter(k.item_group for k in mine if k.item_group and not flags.get(k.item_group))
		if not counts and t.get("item_group") and not flags.get(t.get("item_group")):
			counts = Counter({t.get("item_group"): 0})
		rows.append({"item_code": c, "item_name": t.get("item_name"), "group_counts": dict(counts),
					 "variant_count": len(mine)})
	return rules.consolidation_summary(rows)


def consolidate_templates(target, sources, rename_to=None, confirm_different_products=False, log=None):
	"""Merge each source template into target so every variant sits under one template.

	rename_doc updates every Link, including variants' variant_of, so a template merge carries its
	variants along. That is verified afterwards rather than assumed."""
	log = log or (lambda m: None)
	sources = [s for s in dict.fromkeys(sources or []) if s and s != target]
	rename_to = (rename_to or "").strip() or None
	if not sources and not rename_to:
		raise UserError("Nothing to merge: select more than one template, or give a new code")
	tdoc = load_template(target)
	if rename_to and rename_to != target:
		rules.check_code(rename_to)
		if exists(rename_to):
			raise UserError(f"Cannot rename to {rename_to}: that item code already exists")
	check = consolidation_check(target, sources)
	if check["blocked"]:
		raise UserError(check["block_reason"])
	if check["different_products"] and not confirm_different_products:
		raise UserError("These templates look like different products (" + " / ".join(check["product_names"])
						+ ") - tick the confirmation if they really are one product")

	result = {"template": target, "merged": [], "variants_moved": 0, "renamed_from": None}
	for src in sources:
		sdoc = load_template(src)
		kids = variant_codes(src)
		align = {f: tdoc.get(f) for f in ("stock_uom", "is_stock_item", "has_batch_no", "has_serial_no")
				 if str(sdoc.get(f) or "") != str(tdoc.get(f) or "")}
		if align:  # templates hold no stock, so aligning them to the target is safe
			update_template(src, align, log)
			log(f"template {src}: aligned {sorted(align)} to {target}")
		frappe.rename_doc("Item", src, target, merge=True)
		if exists(src):
			raise UserError(f"{src} still exists after merging into {target}")
		moved = frappe.get_all("Item", filters={"name": ["in", kids], "variant_of": target}, pluck="name") if kids else []
		if len(moved) != len(kids):
			stray = sorted(set(kids) - set(moved))
			raise UserError(f"{len(stray)} variant(s) of {src} did not move under {target}: {stray[:5]}")
		frappe.db.commit()  # each template merge stands on its own, like doing them one by one in the form
		result["merged"].append({"template": src, "variants": len(kids)})
		result["variants_moved"] += len(kids)
		log(f"template {src} -> {target}: {len(kids)} variant(s) moved")

	if rename_to and rename_to != target:
		rename_template(target, rename_to, log=log)
		result["renamed_from"], result["template"] = target, rename_to
	return result


# ---------- step 2: attributes, combinations, new variants ----------

def list_variants(template):
	tdoc, docs, stock = load_family(template)
	return {
		"template": {"item_code": tdoc["name"], "item_name": tdoc.get("item_name"),
					 "attributes": [a["attribute"] for a in tdoc.get("attributes") or []],
					 "is_stock_item": bool(tdoc.get("is_stock_item")), "stock_uom": tdoc.get("stock_uom")},
		"variants": [variant_view(d, stock) for d in docs],
	}


def attribute_values(attribute):
	if not frappe.db.exists("Item Attribute", attribute):
		raise UserError(f"Item Attribute {attribute} does not exist")
	if frappe.db.get_value("Item Attribute", attribute, "numeric_values"):
		raise UserError(f"{attribute} uses numeric ranges - pick an attribute with a value list")
	return [{"value": r.attribute_value, "abbr": r.abbr} for r in
			frappe.get_all("Item Attribute Value", filters={"parent": attribute, "parenttype": "Item Attribute"},
						   fields=["attribute_value", "abbr"], order_by="idx asc")]


def _attribute_tables(attrs):
	vals = {a: attribute_values(a) for a in attrs}
	allowed = {a: {v["value"] for v in vals[a]} for a in attrs}
	abbr = {a: {v["value"]: v["abbr"] for v in vals[a]} for a in attrs}
	return vals, allowed, abbr


def suggest_combinations(template, attributes):
	"""Combinations read from the old variants' names, ready for the variants grid."""
	attrs = rules.check_attributes(attributes)
	tdoc, docs, stock = load_family(template)
	vals, allowed, abbr = _attribute_tables(attrs)
	olds = [d for d in docs if not is_new(d)]
	style = rules.style_name(tdoc, olds, allowed)
	existing = {tuple((a, variant_view(d, stock)["attributes"].get(a)) for a in attrs): d["name"]
				for d in docs if is_new(d)}

	combos, unread = {}, []
	for d in olds:
		got = rules.read_values(d, attrs, allowed)
		if not got:
			unread.append({"item_code": d["name"], "item_name": d.get("item_name")})
			continue
		combos.setdefault(tuple((a, got[a]) for a in attrs), []).append(d["name"])

	order = {a: [v["value"] for v in vals[a]] for a in attrs}
	out = []
	for key in sorted(combos, key=lambda k: tuple(order[a].index(v) for a, v in k)):
		values = dict(key)
		olds_here = combos[key]
		try:
			code, problem = rules.build_code(template, attrs, values, abbr), None
		except UserError as e:
			code, problem = None, str(e)
		qty = sum(stock[c]["qty"] or 0 for c in olds_here)
		ledger = sum(stock[c]["ledger"] for c in olds_here)
		out.append({"values": values, "item_code": code, "problem": problem,
					# a usable code to start from when the abbreviation can't be used as it is
					"suggested_code": code or "-".join([template] + [rules.code_part(abbr[a].get(values[a]), values[a]) for a in attrs]),
					"item_name": " - ".join([style] + [values[a] for a in attrs]),
					"from_old": olds_here, "existing": existing.get(key), "qty": qty, "ledger_count": ledger,
					# No stock history anywhere in the combination: leave it out and the old
					# variants become leftovers to delete (merge when there is data, delete when not).
					"suggested": bool(ledger or qty)})
	return {"template": template, "attributes": attrs, "style_name": style, "combinations": out,
			"unreadable": unread, "values": vals}


def plan_variants(template, attrs, combinations, style_name, tdoc, docs, allowed, abbr):
	if not combinations:
		raise UserError("Tick at least one combination to create")
	olds = [d for d in docs if not is_new(d)]
	style = (style_name or "").strip() or rules.style_name(tdoc, olds, allowed)
	planned, seen = [], set()
	for c in combinations:
		values = c.get("values") or {}
		if set(values) != set(attrs):
			raise UserError(f"Every combination needs a value for {' and '.join(attrs)}")
		for a in attrs:
			if values[a] not in allowed[a]:
				raise UserError(f"'{values[a]}' is not a value of {a}")
		key = tuple(values[a] for a in attrs)
		if key in seen:
			raise UserError(f"{' / '.join(key)} is listed twice")
		seen.add(key)
		# a row may carry its own code / name, typed on the variants grid
		code = rules.check_code(str(c.get("item_code") or "").strip() or rules.build_code(template, attrs, values, abbr))
		name = str(c.get("item_name") or "").strip() or " - ".join([style] + [values[a] for a in attrs])
		planned.append({"values": values, "item_code": code, "item_name": name})
	dup = [k for k, n in Counter(p["item_code"] for p in planned).items() if n > 1]
	if dup:
		raise UserError(f"Item code {dup[0]} is given to more than one new variant")
	return planned


def create_variants(template, attributes, combinations, style_name=None, dry_run=False, log=None):
	"""Create attribute variants under the template with explicit codes and names.

	Codes are set explicitly: create_variant emits doubled dashes while Variant Number is still on
	the template, and it can't be removed until the old variants are merged away."""
	from erpnext.controllers.item_variant import create_variant

	log = log or (lambda m: None)
	attrs = rules.check_attributes(attributes)
	tdoc, docs, stock = load_family(template)
	_, allowed, abbr = _attribute_tables(attrs)
	planned = plan_variants(template, attrs, combinations, style_name, tdoc, docs, allowed, abbr)
	olds = [d for d in docs if not is_new(d)]
	stock_item = 1 if any(d.get("is_stock_item") for d in olds) else int(tdoc.get("is_stock_item") or 0)
	for p in planned:
		p["status"] = "exists" if exists(p["item_code"]) else "planned"
	group_fix = template_group_fix(tdoc)  # raises with a clear message when it can't be fixed
	if dry_run:
		return {"template": template, "dry_run": True, "variants": planned, "template_fixes": group_fix}

	have = [a["attribute"] for a in tdoc.get("attributes") or []]
	upd = {}
	if any(a not in have for a in attrs):
		upd["attributes"] = template_attribute_rows(tdoc) + [{"attribute": a} for a in attrs if a not in have]
	if int(tdoc.get("is_stock_item") or 0) != stock_item:
		upd["is_stock_item"] = stock_item
	if upd or group_fix:  # new variants copy the template's item group, so fix it before creating them
		update_template(template, upd, log)
		log(f"template {template}: {', '.join(sorted({**group_fix, **upd}))} updated")
		frappe.db.commit()

	for p in planned:
		if p["status"] == "exists":
			continue
		frappe.db.savepoint("item_merge_variant")
		try:
			doc = create_variant(template, p["values"])
			doc.item_code = p["item_code"]
			doc.item_name = p["item_name"]
			doc.ifw_retailskusuffix = p["item_code"]
			doc.is_stock_item = stock_item
			doc.set("attributes", [a for a in doc.get("attributes") or [] if a.attribute != VARIANT_NUMBER])
			doc.insert()
			p["status"] = "created"
			log(f"created {p['item_code']} {p['item_name']}")
		except Exception as e:
			frappe.db.rollback(save_point="item_merge_variant")
			p["status"], p["error"] = "failed", message_of(e)[:300]
			log(f"FAILED creating {p['item_code']}: {p['error'][:200]}")
	created = [p["item_code"] for p in planned if p["status"] == "created"]
	if created:
		add_activity(template, f"created {len(created)} variant(s) with {' + '.join(attrs)}: {', '.join(created[:20])}")
	return {"template": template, "dry_run": False, "variants": planned}


def message_of(e):
	"""An exception as a person reads it: frappe.throw's text without markup."""
	return re.sub(r"<[^>]+>", "", str(e) or e.__class__.__name__).strip()


# ---------- step 3: line up old and new ----------

def alignment(template):
	tdoc, docs, stock = load_family(template)
	empty = {c: s["ledger"] == 0 and s["qty"] == 0 for c, s in stock.items()}
	plan = plan_pairs(tdoc, docs, empty)
	by = {d["name"]: d for d in docs}
	rows = []
	for p in plan["pairs"]:
		old, new = by[p["old"]], by[p["new"]]
		issues, fixes = rules.settings_diff(old, new, stock[p["new"]]["ledger"])
		rows.append({"old": variant_view(old, stock), "new": variant_view(new, stock),
					 "status": "blocked" if issues else ("fix" if fixes else "ready"), "issues": issues, "fixes": fixes})
	for u in plan["unmatched"]:
		rows.append({"old": variant_view(by[u["old"]], stock), "new": None,
					 "status": "leftover" if u["empty"] else "unmatched", "issues": [u["reason"]], "fixes": {}})
	for c in plan["conflicts"]:
		for o in c["olds"]:
			rows.append({"old": variant_view(by[o], stock), "new": None, "status": "unmatched",
						 "issues": [f"{len(c['olds'])} old variants resolve to {c['new']}; align by hand"], "fixes": {}})
	for a in plan["ambiguous"]:
		rows.append({"old": variant_view(by[a["old"]], stock), "new": None, "status": "unmatched",
					 "issues": [f"could match {', '.join(a['candidates'])}; align by hand"], "fixes": {}})
	return {"template": {"item_code": tdoc["name"], "item_name": tdoc.get("item_name"),
						 "attributes": [a["attribute"] for a in tdoc.get("attributes") or []]},
			"rows": rows, "unpaired_new": [variant_view(by[n], stock) for n in plan["unused_new"]],
			"attribute_roles": {"colour": plan["colour_attribute"], "size": plan["size_attribute"]}}


def check_plan(template, pairs, leftovers=None):
	"""Validate the pairs as lined up by hand. Nothing is written."""
	leftovers = list(dict.fromkeys(leftovers or []))
	tdoc, docs, stock = load_family(template)
	by = {d["name"]: d for d in docs}
	problems, rows = [], []
	olds = [p.get("old") for p in pairs]
	news = [p.get("new") for p in pairs]
	for label, seq in (("old", olds), ("new", news)):
		dup = [c for c, n in Counter(seq).items() if c and n > 1]
		if dup:
			problems.append(f"{', '.join(dup)} used more than once on the {label} side")
	for p in pairs:
		o, n = p.get("old"), p.get("new")
		if o not in by:
			problems.append(f"{o} is not a variant of {template}")
			continue
		if n not in by:
			problems.append(f"{n} is not a variant of {template}")
			continue
		if is_new(by[o]):
			problems.append(f"{o} already uses real attributes - it is not an old variant")
		if not is_new(by[n]):
			problems.append(f"{n} is a Variant Number item - merge into an attribute variant")
		issues, fixes = rules.settings_diff(by[o], by[n], stock[n]["ledger"])
		rows.append({"old": o, "new": n, "issues": issues, "fixes": fixes})
		problems += [f"{o} -> {n}: {i}" for i in issues]
	for c in leftovers:
		if c not in by:
			problems.append(f"{c} is not a variant of {template}")
		elif stock[c]["ledger"] or stock[c]["qty"]:
			problems.append(f"{c} has stock history and cannot be deleted as a leftover")
		elif c in olds:
			problems.append(f"{c} is both merged and marked as a leftover")
	return {"ok": not problems, "problems": problems, "pairs": rows, "needs_fix": sum(bool(r["fixes"]) for r in rows)}


def fix_settings(template, pairs, log=None):
	"""Align stock settings on NEW variants to their old counterparts, where safe."""
	log = log or (lambda m: None)
	changed = []
	for r in check_plan(template, pairs)["pairs"]:
		if r["fixes"] and not r["issues"]:
			doc = frappe.get_doc("Item", r["new"])
			doc.update(r["fixes"])
			doc.save()
			changed.append({"item_code": r["new"], "set": r["fixes"]})
			log(f"{r['new']}: set {r['fixes']} to match {r['old']}")
	return {"changed": changed, "check": check_plan(template, pairs)}


# ---------- after a merge ----------

def current_codes(codes):
	"""Where each item code lives now. A code that no longer exists was renamed or merged away;
	Item Merge History records both, so follow it (newest row first) until an item exists."""
	codes = list(dict.fromkeys(codes or []))
	have = set(frappe.get_all("Item", filters={"name": ["in", codes]}, pluck="name")) if codes else set()
	out = {}
	for c in codes:
		seen, code = {c}, c
		for _ in range(6):
			if code in have:
				break
			nxt = frappe.get_all("Item Merge History", filters={"old_item_code": code}, pluck="new_item_code",
								 order_by="creation desc", limit_page_length=1)
			if not nxt or nxt[0] in seen:
				break
			code = nxt[0]
			seen.add(code)
			if exists(code):
				have.add(code)
		out[c] = code
	return out


PENDING_REPOSTS = ["Queued", "In Progress"]


def reposts(template):
	codes = [template] + variant_codes(template)
	pending = frappe.get_all("Repost Item Valuation", filters={"item_code": ["in", codes], "status": ["in", PENDING_REPOSTS]},
							 fields=["item_code", "status"])
	failed = frappe.get_all("Repost Item Valuation", filters={"item_code": ["in", codes], "status": "Failed"},
							fields=["item_code", "creation"])
	worker = frappe.get_all("Scheduled Job Type", filters={"method": ["like", "%repost_entries%"]},
							fields=["frequency", "last_execution", "stopped"], limit_page_length=1)
	return {"pending": len(pending), "running": sum(r.status == "In Progress" for r in pending),
			"failed": [{"item_code": r.item_code, "at": r.creation} for r in failed],
			"worker": ({"frequency": worker[0].frequency, "last_run": worker[0].last_execution,
						"stopped": bool(worker[0].stopped)} if worker else None)}
