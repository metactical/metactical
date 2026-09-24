"""Item Merge rules that need no database: codes, names, attribute reading, settings checks.

Kept free of frappe so the offline tests (item_merge/tests) run without a bench.
"""
import re

from metactical.item_merge.pairing import COLOUR_ALIASES, SIZE_ALIASES, SUFFIX_COLOUR, VARIANT_NUMBER, name_tokens, resolve

ALIASES = {**COLOUR_ALIASES, **SIZE_ALIASES}

# Stock settings ERPNext compares on a merge. A transacted item's settings are locked.
SETTINGS = ("stock_uom", "is_stock_item", "has_batch_no", "has_serial_no", "is_fixed_asset")
PREFLIGHT_FLAGS = ("is_stock_item", "has_batch_no", "has_serial_no", "is_fixed_asset")

BAD_CODE = re.compile(r"[\s/\\%#?]")
BAD_CODE_MESSAGE = "can't be an item code (no spaces or / \\ % # ?)"


class UserError(Exception):
	"""A problem the person using the page can fix. The page API shows it with frappe.throw."""


# ---------- codes and names ----------

def base_code(code):
	"""RVX4184BLK -> RVX4184: drop the trailing colour letters after the last digit."""
	stripped = re.sub(r"[A-Za-z]+$", "", code or "")
	return stripped if re.search(r"\d$", stripped) else code


def product_name(item_name):
	"""The product without colour / size: the first ' - ' part of a template's item name."""
	return (item_name or "").split(" - ")[0].strip()


def base_sku(code):
	return base_code((code or "").split("-")[0])


def check_code(code):
	if BAD_CODE.search(code or ""):
		raise UserError(f"'{code}' {BAD_CODE_MESSAGE}")
	return code


def code_part(abbr, value):
	"""An abbreviation usable in an item code: letters and digits only ('Coyo Brn' -> 'CoyoBrn')."""
	return re.sub(r"[^A-Za-z0-9]", "", abbr or "") or re.sub(r"[^A-Za-z0-9]", "", value or "")


def build_code(template, attrs, values, abbr):
	missing = [a for a in attrs if not abbr[a].get(values[a])]
	if missing:
		raise UserError(f"No abbreviation on {missing[0]} = {values[missing[0]]}; add one in Item Attribute first")
	# some abbreviations carry their own dash (Colour - Actual Black is "-001"); never emit "--"
	parts = [abbr[a][values[a]].strip("-") for a in attrs]
	bad = [(a, values[a], abbr[a][values[a]]) for a, p in zip(attrs, parts) if not re.fullmatch(r"[A-Za-z0-9]+", p)]
	if bad:
		a, v, ab = bad[0]
		raise UserError(f"{a} = {v} has abbreviation '{ab}', which can't go in an item code; "
						f"pick another attribute or fix the abbreviation")
	return "-".join([template] + parts)


def check_attributes(attrs, legacy=VARIANT_NUMBER):
	"""`legacy` is the family's own numeric attribute, read from its template - never a guess."""
	attrs = [a for a in (attrs or []) if a]
	if not 1 <= len(attrs) <= 2:
		raise UserError("Choose one or two item attributes")
	if len(set(attrs)) != len(attrs):
		raise UserError("Choose two different attributes")
	if legacy in attrs:
		raise UserError(f"{legacy} is the attribute being replaced")
	return attrs


# ---------- reading attribute values out of old item names ----------

def alias_map():
	"""{attribute value: [other wordings that mean it]} - the alias tables inverted.

	The align screen needs this to tell whether an old item's name really mentions the new variant's
	values ("... - L" does mean Large). It is sent with the alignment rather than kept as a second
	copy in the Vue component: the copy there had drifted and no longer knew S, M, L or XXS, so every
	single-letter size raised a spurious "names differ" warning."""
	out = {}
	for alias, value in {**SIZE_ALIASES, **COLOUR_ALIASES}.items():
		out.setdefault(value, []).append(alias)
	return {value: sorted(aliases) for value, aliases in out.items()}


def role_aliases(attribute):
	if re.search(r"colou?r", attribute, re.I):
		return COLOUR_ALIASES
	if re.search(r"size", attribute, re.I):
		return SIZE_ALIASES
	return ALIASES


def resolve_loose(token, allowed, aliases):
	"""resolve(), then - for suggestions only, never for pairing - the one allowed value the token
	starts with, word for word ("Midnight Navy Blue" -> "Midnight Navy"). Longest wins; a tie is no match."""
	v = resolve(token, allowed, aliases)
	if v or not token:
		return v
	norm = lambda x: re.sub(r"[\s\-/]+", " ", str(x)).strip().lower()  # noqa: E731
	t = norm(token)
	hits = sorted((a for a in allowed if t.startswith(norm(a) + " ")), key=lambda a: -len(norm(a)))
	if not hits or (len(hits) > 1 and len(norm(hits[0])) == len(norm(hits[1]))):
		return None
	return hits[0]


def read_values(doc, attrs, allowed):
	"""Attribute values encoded in an old variant's item_name, or None if it can't be read."""
	tokens = name_tokens(doc.get("item_name"))
	if len(attrs) == 1:
		a = attrs[0]
		for tok in reversed(tokens[-2:]):
			v = resolve_loose(tok, allowed[a], role_aliases(a))
			if v:
				return {a: v}
		suffix = re.sub(r"^.*\d", "", doc.get("variant_of") or "")
		v = resolve_loose(SUFFIX_COLOUR.get(suffix), allowed[a], role_aliases(a))
		return {a: v} if v else None
	a1, a2 = attrs
	if len(tokens) >= 2:
		for t1, t2 in ((tokens[-2], tokens[-1]), (tokens[-1], tokens[-2])):
			v1, v2 = resolve_loose(t1, allowed[a1], role_aliases(a1)), resolve_loose(t2, allowed[a2], role_aliases(a2))
			if v1 and v2:
				return {a1: v1, a2: v2}
	# colour missing from the name: fall back to the legacy colour-template suffix
	suffix = SUFFIX_COLOUR.get(re.sub(r"^.*\d", "", doc.get("variant_of") or ""))
	for colour_attr, other in ((a1, a2), (a2, a1)):
		c = resolve_loose(suffix, allowed[colour_attr], COLOUR_ALIASES)
		o = next((resolve_loose(t, allowed[other], role_aliases(other)) for t in reversed(tokens[-2:])), None) \
			if tokens else None
		if c and o:
			return {colour_attr: c, other: o}
	return None


def style_name(template_doc, old_docs, allowed):
	"""The product name without colour/size: the shared start of every old variant's name,
	minus trailing tokens that are values of the selected attributes.

	Stripping a fixed number of tokens is wrong when only one attribute is chosen: the old
	names still end in a size, so 'Shirt - Black - Small' would keep 'Black' in the style."""
	token_lists = [name_tokens(d.get("item_name")) for d in old_docs if d.get("item_name")]
	if not token_lists:
		return template_doc.get("item_name") or template_doc["name"]
	prefix = []
	for group in zip(*token_lists):
		if len(set(group)) != 1:
			break
		prefix.append(group[0])
	values = set().union(*allowed.values()) if allowed else set()
	while len(prefix) > 1 and any(resolve(prefix[-1], values, a) for a in (COLOUR_ALIASES, SIZE_ALIASES, {})):
		prefix.pop()
	if prefix and len(prefix) < min(len(t) for t in token_lists):
		return " - ".join(prefix)
	return template_doc.get("item_name") or template_doc["name"]


# ---------- stock settings ----------

def settings_diff(old, new, new_ledger):
	"""What differs between old and new, and whether fixing it on the new item is safe."""
	issues, fixes = [], {}
	for f in SETTINGS:
		o, n = old.get(f), new.get(f)
		same = (o or "") == (n or "") if f == "stock_uom" else int(o or 0) == int(n or 0)
		if same:
			continue
		if new_ledger:  # a transacted item's uom/stock settings are locked by ERPNext
			issues.append(f"{f}: old {o} vs new {n}, and the new item already has stock history")
		else:
			fixes[f] = o
	return issues, fixes


def preflight(old, new):
	"""Right before a merge: what ERPNext would refuse, and the one known trap fixed on the new item."""
	issues, fixes = [], {}
	if (old.get("stock_uom") or "") != (new.get("stock_uom") or ""):
		issues.append(f"stock_uom old={old.get('stock_uom')} new={new.get('stock_uom')}")
	for f in PREFLIGHT_FLAGS:
		if int(old.get(f) or 0) != int(new.get(f) or 0):
			if f == "is_stock_item" and int(old.get(f) or 0) and not int(new.get(f) or 0):
				fixes[f] = 1  # the known trap: fix the new item, don't skip validation
			else:
				issues.append(f"{f} old={old.get(f)} new={new.get(f)}")
	return issues, fixes


# ---------- child rows ----------

def dedupe_suppliers(rows):
	"""A new variant copies the template's supplier row (often without a part number), then the merge
	brings the old variant's row for the same supplier with its part number: two rows, one blank.
	Drop a blank-part-number row when the same supplier has a row with one, and exact repeats."""
	with_part = {r.get("supplier") for r in rows if (r.get("supplier_part_no") or "").strip()}
	seen, keep = set(), []
	for r in rows:
		part = (r.get("supplier_part_no") or "").strip()
		if not part and r.get("supplier") in with_part:
			continue
		key = (r.get("supplier"), part)
		if key in seen:
			continue
		seen.add(key)
		keep.append(r)
	return keep


def pricing_rule_blocker(message):
	"""The Pricing Rule named in ERPNext's 'linked with' refusal, or None.

	Match 'Pricing Rule' explicitly: a lazy [A-Za-z ]+? splits it into doctype 'Pricing'."""
	m = re.search(r"linked with Pricing Rule\s*(?:<a[^>]*>)?\s*([A-Za-z0-9\-/_.]+)", re.sub(r"<[^>]+>", " ", message or ""))
	return m.group(1) if m else None


# ---------- template merge safeguards ----------

def consolidation_summary(rows):
	"""rows: [{item_code, item_name, group_counts, variant_count}] for the target and each source.
	Do they look like one product, and would the result be saveable (one item group)?"""
	out = []
	for r in rows:
		counts = dict(sorted((r.get("group_counts") or {}).items()))
		out.append({"item_code": r["item_code"], "item_name": r.get("item_name"),
					"product_name": product_name(r.get("item_name")), "base_sku": base_sku(r["item_code"]),
					"item_groups": sorted(counts), "group_counts": counts,
					"variant_count": r.get("variant_count") or 0})
	names = sorted({r["product_name"] for r in out if r["product_name"]}, key=str.lower)
	groups = sorted({g for r in out for g in r["item_groups"]})
	reason = ""
	if len(groups) > 1:
		reason = ("The variants use " + str(len(groups)) + " item groups - "
				  + "; ".join(f"{g}: " + ", ".join(f"{r['item_code']} ({r['group_counts'][g]})" for r in out if g in r["group_counts"])
							  for g in groups)
				  + ". Set every variant (and template) to the same item group before merging")
	return {"templates": out, "product_names": names, "item_groups": groups,
			"different_products": len({n.lower() for n in names}) > 1,
			"blocked": len(groups) > 1, "block_reason": reason}


# ---------- item changes (the Item codes screen) ----------

def plan_changes(template, family, changes):
	"""Validate edits to a template's variants. family: {item_code: {item_name, ifw_retailskusuffix}}.
	Returns (rows, problems); rows only for variants that really change."""
	rows, problems = [], []
	for c in changes or []:
		code = str(c.get("item_code") or "").strip()
		cur = family.get(code)
		if not cur:
			problems.append(f"{code or '(blank)'} is not a variant of {template}")
			continue
		row = {"item_code": code, "new_code": None, "new_item_name": None, "new_retail_sku": None}
		for field, key, label in (("item_name", "item_name", "item name"), ("retail_sku", "ifw_retailskusuffix", "retail SKU")):
			if field in c and c[field] is not None:
				v = str(c[field]).strip()
				if not v:
					problems.append(f"{code}: {label} is empty")
				elif v != (cur.get(key) or ""):
					row["new_" + field] = v
		new_code = str(c.get("new_code") or "").strip()
		if new_code and new_code != code:
			if BAD_CODE.search(new_code):
				problems.append(f"'{new_code}' {BAD_CODE_MESSAGE}")
			row["new_code"] = new_code
		if row["new_code"] or row["new_item_name"] or row["new_retail_sku"]:
			rows.append(row)

	new_codes = [r["new_code"] for r in rows if r["new_code"]]
	problems += [f"{k} is given to more than one item" for k in sorted({x for x in new_codes if new_codes.count(x) > 1})]
	final_sku = {code: (r.get("ifw_retailskusuffix") or "") for code, r in family.items()}
	for r in rows:
		if r["new_retail_sku"]:
			final_sku[r["item_code"]] = r["new_retail_sku"]
	skus = [v for v in final_sku.values() if v]
	problems += [f"retail SKU {k} would be on more than one variant" for k in sorted({s for s in skus if skus.count(s) > 1})]
	return rows, problems


def pair_edit_problems(pairs):
	"""The item name / retail SKU typed per pair on the align screen."""
	problems = []
	for p in pairs:
		for field, label in (("item_name", "item name"), ("retail_sku", "retail SKU")):
			if field in p and not str(p[field] or "").strip():
				problems.append(f"{p.get('new')}: {label} is empty")
	skus = [str(p["retail_sku"]).strip() for p in pairs if p.get("retail_sku")]
	problems += [f"retail SKU {k} is used on more than one new variant" for k in sorted({s for s in skus if skus.count(s) > 1})]
	return problems
