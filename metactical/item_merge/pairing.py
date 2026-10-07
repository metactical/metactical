"""Old -> new variant pairing for the item-merge project. Pure functions, no network.

An "old" variant is a legacy Variant-Number item whose real size/colour lives only in
its item_name. A "new" variant carries proper Item Attributes. Pairing takes the old
variant's values - read by `attribute_ai`, or off the name tail here when the AI could
not answer - and matches them to the new variant's attribute values.

The matching, the conflict detection and the ambiguity split below are deliberately not
the AI's job. Getting a pair wrong moves an item's stock and ledger onto another item,
so what decides that stays here, where it is the same answer every time.

Never pair by the numeric suffix: legacy `-0001..-0006` is offset by one from the size
abbreviations `0002..0007`, so suffix matching silently moves stock to the wrong size.
"""
import re

# The conventional name of the legacy numeric attribute. Only a fallback: the attribute a given
# family actually uses is read off its own template (variant_attribute below), and the site-wide
# answer comes from ERPNext via catalogue.variant_attribute().
VARIANT_NUMBER = "Variant Number"

# item_name wording -> Item Attribute value. Extend as new families surface new wording.
SIZE_ALIASES = {
	"XS": "XSmall", "XXS": "XXSmall", "S": "Small", "M": "Medium", "L": "Large",
	"XL": "XLarge", "XXL": "2XLarge", "XXLarge": "2XLarge", "2XL": "2XLarge",
	"XXXL": "3XLarge", "XXXLarge": "3XLarge", "3XL": "3XLarge",
}
COLOUR_ALIASES = {
	"Woodland": "Camo - Woodland", "Woodland Camo": "Camo - Woodland",
	"Black Camo": "Camo - Black", "City Camo": "Camo - City/Urban",
	"Olive Drab": "Olive", "OD": "Olive", "Olive Drap": "Olive",
	"Midnight Navy Blue": "Midnight Navy",
}
# Legacy per-colour template suffix -> colour, used when the name carries no colour.
SUFFIX_COLOUR = {
	"BLK": "Black", "WHT": "White", "OLV": "Olive", "OD": "Olive", "NVY": "Navy",
	"TAN": "Tan", "WLD": "Camo - Woodland", "CTC": "Camo - City/Urban",
}


def variant_attribute(template_doc):
	"""The legacy attribute this family hangs off: the numeric one on its own template.

	Read from the document rather than assumed, so a family that uses a differently named numeric
	attribute still works. Falls back to the conventional name when the template says nothing."""
	for a in template_doc.get("attributes") or []:
		if a.get("numeric_values") and a.get("attribute"):
			return a["attribute"]
	return VARIANT_NUMBER


def real_attributes(doc, legacy=VARIANT_NUMBER):
	"""{attribute: value} for every attribute that has a value and is not the legacy one."""
	return {a["attribute"]: a["attribute_value"]
			for a in doc.get("attributes") or []
			if a.get("attribute") != legacy and a.get("attribute_value")}


def is_new(doc, legacy=VARIANT_NUMBER):
	return bool(real_attributes(doc, legacy))


def attribute_roles(template_doc):
	"""Which template attribute is the colour and which is the size (either may be None)."""
	legacy = variant_attribute(template_doc)
	colour = size = None
	for a in template_doc.get("attributes") or []:
		name = a.get("attribute") or ""
		if name == legacy:
			continue
		if colour is None and re.search(r"colou?r", name, re.I):
			colour = name
		elif size is None and re.search(r"size", name, re.I):
			size = name
	return colour, size


def _norm(s):
	return re.sub(r"[\s\-/]+", " ", str(s or "")).strip().lower()


def resolve(token, allowed, aliases):
	"""Map an item_name token onto one of the allowed attribute values, or None."""
	if not token:
		return None
	if token in allowed:
		return token
	aliased = aliases.get(token)
	if aliased in allowed:
		return aliased
	by_norm = {_norm(v): v for v in allowed}
	if _norm(token) in by_norm:
		return by_norm[_norm(token)]
	if aliased and _norm(aliased) in by_norm:
		return by_norm[_norm(aliased)]
	return None


def name_tokens(item_name):
	return [t.strip() for t in str(item_name or "").split(" - ") if t.strip()]


def plan_pairs(template_doc, variants, emptiness=None, values=None):
	"""Pair old variants to new ones.

	variants: item docs (dicts) that are variants of the template or of named source
			  templates. emptiness: optional {item_code: True} for zero-bin, zero-ledger items.
	values:   optional {item_code: {attribute: value}} read by attribute_ai. Where an old variant
			  is in there, those values are used instead of picking the name apart here - reading
			  the name is the part that was inaccurate. An old variant the AI did not answer for
			  falls back to the tables below, so a partial answer still pairs the rest.

	Returns a dict describing pairs and everything that could not be paired safely.
	"""
	emptiness = emptiness or {}
	values = values or {}
	legacy = variant_attribute(template_doc)
	colour_attr, size_attr = attribute_roles(template_doc)
	news = [v for v in variants if is_new(v, legacy)]
	olds = [v for v in variants if not is_new(v, legacy)]

	allowed_size = {real_attributes(n, legacy).get(size_attr) for n in news} - {None}
	allowed_colour = {real_attributes(n, legacy).get(colour_attr) for n in news} - {None}

	pairs, unmatched, ambiguous = [], [], []
	for o in olds:
		tokens = name_tokens(o.get("item_name"))
		read = values.get(o["name"]) or {}
		size = read.get(size_attr) if size_attr else None
		colour = read.get(colour_attr) if colour_attr else None
		colour_token = None

		if size_attr and size is None:
			size = resolve(tokens[-1] if tokens else None, allowed_size, SIZE_ALIASES)
		if colour_attr and colour is None:
			# "Style - Colour - Size" puts the colour second from last; a colour-only family
			# ("Style - 3Pcs - Black") ends in it, so try the last part first there.
			colour_tokens = tokens[-2:-1] if size_attr else tokens[-1:] + tokens[-2:-1]
			colour_token = colour_tokens[0] if colour_tokens else None
			colour = next((c for c in (resolve(t, allowed_colour, COLOUR_ALIASES) for t in colour_tokens) if c), None)
			if colour is None:
				suffix = re.sub(r"^.*\d", "", o.get("variant_of") or "")   # greedy: after the LAST digit
				colour = resolve(SUFFIX_COLOUR.get(suffix), allowed_colour, COLOUR_ALIASES)

		# A value the AI read has to be one the new variants actually carry, or it pairs nothing.
		if size is not None and size not in allowed_size:
			size = None
		if colour is not None and colour not in allowed_colour:
			colour = None

		# What was read, and by what, so the message says what actually happened rather than
		# blaming the name when the value came from the AI and simply is not on a new variant.
		reason = None
		if size_attr and size is None:
			said = read.get(size_attr)
			reason = (f"size '{said}' is not on any new variant {sorted(allowed_size)}" if said
					  else f"size '{tokens[-1] if tokens else ''}' not among new variants {sorted(allowed_size)}")
		elif colour_attr and colour is None:
			said = read.get(colour_attr)
			if said:
				reason = f"colour '{said}' is not on any new variant {sorted(allowed_colour)}"
			elif colour_token:
				reason = f"colour '{colour_token}' not among new variants {sorted(allowed_colour)}"
			else:
				reason = "no colour in item_name or template suffix"
		if reason:
			unmatched.append({"old": o["name"], "old_name": o.get("item_name"),
							  "reason": reason, "empty": bool(emptiness.get(o["name"]))})
			continue

		cands = [n for n in news
				 if (not size_attr or real_attributes(n, legacy).get(size_attr) == size)
				 and (not colour_attr or real_attributes(n, legacy).get(colour_attr) == colour)]
		if len(cands) == 1:
			pairs.append({"old": o["name"], "new": cands[0]["name"], "old_name": o.get("item_name"),
						  "size": size, "colour": colour, "empty": bool(emptiness.get(o["name"]))})
		elif not cands:
			unmatched.append({"old": o["name"], "old_name": o.get("item_name"),
							  "reason": f"no new variant for colour={colour} size={size}",
							  "empty": bool(emptiness.get(o["name"]))})
		else:
			ambiguous.append({"old": o["name"], "candidates": [c["name"] for c in cands]})

	# Two olds landing on one new is the damaging case: fields_to_overwrite would push the
	# second old's values onto an item that already holds the first old's stock.
	by_new = {}
	for p in pairs:
		by_new.setdefault(p["new"], []).append(p["old"])
	conflicts = [{"new": n, "olds": o} for n, o in by_new.items() if len(o) > 1]
	conflicted = {o for c in conflicts for o in c["olds"]}
	safe_pairs = [p for p in pairs if p["old"] not in conflicted]

	used = {p["new"] for p in safe_pairs}
	return {
		"template": template_doc["name"],
		"colour_attribute": colour_attr,
		"size_attribute": size_attr,
		"pairs": safe_pairs,
		"conflicts": conflicts,
		"ambiguous": ambiguous,
		"unmatched": unmatched,
		# Unmatched AND empty is the only leftover that is safe to delete.
		"leftovers": [u for u in unmatched if u["empty"]],
		"blocked": [u for u in unmatched if not u["empty"]],
		"unused_new": sorted(n["name"] for n in news if n["name"] not in used),
	}


def clean_code(code):
	"""Collapse the empty-segment dashes create_variant emits while Variant Number lingers."""
	return re.sub(r"-{2,}", "-", code)
