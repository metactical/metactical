"""Reading a legacy variant's real attribute values out of its item_name, with an AI.

This is the one genuinely fuzzy step in the whole merge. A legacy variant carries no attributes -
its colour and size live in wording a person wrote, and the wording is not consistent: `OD`,
`Olive Drab` and `Olive Drap` are all `Olive`; `L`, `Lg` and `Large` are all `Large`; the colour is
sometimes not in the name at all and has to come off the template's suffix. `rules.read_values` did
this with hand-maintained alias tables, which is why it kept being wrong - every family that used a
wording nobody had added yet came back unreadable.

Both screens that were inaccurate ask the same question, so they share one answer:

  * **Suggest combinations** turns each old variant's values into the combination to create.
  * **Align** matches each old variant to the new variant carrying those values.

Everything downstream of this stays exactly as it was and stays deterministic: the grouping, the
old -> new matching, the "two old variants resolve to one new one" block, the ambiguity and
leftover split, and the stock checks. The AI reads names. It does not decide what gets merged.

**One answer per old variant, never more.** The model is given a numbered list and must return
that same set of numbers. Anything it invents is dropped, so N old variants can only ever produce
at most N combinations - one extra would be a combination with no variant behind it, which the
grid cannot pair and the operator would have to notice.

**Cost.** Three things keep this small: the shared style prefix is stripped from every name, so
only the part that varies is sent; the variants are numbered rather than named, so an item code is
never paid for twice; and the answer is positional JSON (`{"1":["Olive","Large"]}`) rather than
objects repeating the attribute names on every row. A 42-variant family costs roughly one short
paragraph in and one short paragraph out.
"""
import hashlib
import json

import frappe

from metactical.ai.client import AIUnavailable, ask_json
from metactical.item_merge import rules

FEATURE = "Item Merge - Read Attributes"

# Both screens ask the same question about the same family, and the align screen re-asks it every
# time it refreshes after a fix or a check. The answer only changes when the names, the attributes
# or the allowed values change, all of which are in the key - so a family is paid for once a day,
# not once a click.
CACHE_PREFIX = "item_merge_attr_ai"
CACHE_TTL = 24 * 60 * 60

SYSTEM = (
	"You map product variant names onto a fixed list of attribute values.\n"
	"For each numbered name, pick exactly one value per attribute, copied verbatim from the "
	"allowed list for that attribute.\n"
	"The name uses trade wording: OD and Olive Drab mean Olive, L means Large, XXL means 2XLarge, "
	"Woodland means a woodland camo value, and so on. Match on meaning, not on spelling.\n"
	"Use null for an attribute you cannot determine from the name. Never invent a value that is "
	"not in the allowed list, and never guess to avoid a null.\n"
	"Answer with JSON only: {\"items\":{\"<number>\":[<value for attribute 1>,...]}}. "
	"Include every number you were given, and no others."
)


def _common_prefix(names, allowed=None):
	"""The " - " separated head every name shares, minus anything that is itself an answer.

	The shared head is normally the style, which carries no attribute value and is pure cost to
	send. But a legacy family is often **all one colour** - that is what a per-colour template is -
	so the colour is in every name and therefore in the shared head. Stripping it asks the model to
	read a colour out of "30 x 30", which it cannot do, and it correctly answers null for every row.

	So trailing tokens that resolve to one of the values being asked about are put back.
	`rules.style_name` has guarded against the same thing since the start; this did not.
	"""
	token_lists = [rules.name_tokens(n) for n in names if n]
	if len(token_lists) < 2:
		return []
	prefix = []
	for group in zip(*token_lists):
		if len(set(group)) != 1:
			break
		prefix.append(group[0])

	values = set().union(*allowed.values()) if allowed else set()
	while prefix and rules.resolve_loose(prefix[-1], values, rules.ALIASES):
		prefix.pop()

	# Never strip a whole name: a family where two variants share everything but the last token
	# would otherwise send an empty string.
	return prefix[:min(len(t) for t in token_lists) - 1]


def _short_names(olds, allowed=None):
	"""{item_code: the part of the name that carries an answer}."""
	names = [d.get("item_name") or "" for d in olds]
	drop = len(_common_prefix(names, allowed))
	out = {}
	for d in olds:
		tokens = rules.name_tokens(d.get("item_name"))
		tail = tokens[drop:] if drop and len(tokens) > drop else tokens
		out[d["name"]] = " - ".join(tail) or (d.get("item_name") or d["name"])
	return out


def _suffix_hint(olds):
	"""The legacy per-colour template suffix, when the family has one worth mentioning.

	Some names carry no colour at all and the colour is only in the template code (…-BLK). Sending
	the suffix is two tokens and turns those from unreadable into readable.
	"""
	suffixes = {str(d.get("variant_of") or "").rsplit("-", 1)[-1] for d in olds}
	suffixes = {s for s in suffixes if s and not s.isdigit() and len(s) <= 4}
	return sorted(suffixes)


def _batches(codes, size):
	size = max(1, int(size or 60))
	return [codes[i:i + size] for i in range(0, len(codes), size)]


def _ask(template, attrs, allowed, short, codes, suffixes):
	"""One request for one batch. Returns {item_code: {attribute: value}} for what came back clean."""
	numbered = {str(i + 1): code for i, code in enumerate(codes)}
	lines = "\n".join("{0} {1}".format(n, short[c]) for n, c in numbered.items())
	body = {
		"attributes": [{"name": a, "allowed": sorted(allowed[a])} for a in attrs],
	}
	if suffixes:
		body["template_colour_suffixes"] = suffixes
	user = "{0}\n\nnames:\n{1}".format(json.dumps(body, separators=(",", ":")), lines)

	answer = ask_json(FEATURE, SYSTEM, user, reference=template)
	items = answer.get("items")
	if not isinstance(items, dict):
		raise AIUnavailable("the answer had no items object")

	# Canonical spelling wins: the model is told to copy verbatim, but a stray case difference is
	# not a reason to throw a whole family away.
	canon = {a: {str(v).strip().lower(): v for v in allowed[a]} for a in attrs}

	out = {}
	for key, values in items.items():
		code = numbered.get(str(key).strip())
		if not code or code in out:
			continue  # invented or repeated - the operator asked about these names, not others
		if not isinstance(values, list):
			continue
		got = {}
		for attr, value in zip(attrs, values):
			if value is None:
				continue
			resolved = canon[attr].get(str(value).strip().lower())
			if resolved:
				got[attr] = resolved
		if got:
			out[code] = got
	return out


def _cache_key(template, attrs, allowed, short):
	"""Identifies the exact question. Any change to it is a different question.

	The model is in the key: switching it in AI Settings and still being served yesterday's answers
	from the model you switched away from is the opposite of what changing it is for.
	"""
	model = frappe.db.get_single_value("AI Settings", "model") or ""
	payload = json.dumps([model, template, attrs, {a: sorted(allowed[a]) for a in attrs},
						  sorted(short.items())], separators=(",", ":"))
	return "{0}:{1}".format(CACHE_PREFIX, hashlib.sha1(payload.encode("utf-8")).hexdigest())


def read_values(template, olds, attrs, allowed, refresh=False):
	"""{item_code: {attribute: value}} for these old variants, and a warning when the AI was no help.

	Returns (values, warning). `warning` is None when the AI answered; otherwise it is a sentence
	for the operator saying what went wrong, and `values` holds whatever was read before it stopped
	so the caller falls back to `rules.read_values` for the rest. A variant the model left out
	simply falls back with the others.

	`refresh=True` asks again rather than reusing the cached answer.
	"""
	olds = [d for d in olds if d.get("name")]
	if not olds or not attrs:
		return {}, None

	short = _short_names(olds, allowed)
	key = _cache_key(template, attrs, allowed, short)
	if not refresh:
		# expires=True because this key has a TTL. Without it a miss is written back into
		# frappe.local.cache as None, and set_value below - which skips the local copy whenever
		# there is a TTL - cannot displace it, so nothing would ever hit within one request.
		cached = frappe.cache().get_value(key, expires=True)
		if cached is not None:
			return cached, None

	suffixes = _suffix_hint(olds)
	codes = [d["name"] for d in olds]
	size = frappe.db.get_single_value("AI Settings", "max_items_per_request") or 60

	values = {}
	for batch in _batches(codes, size):
		try:
			values.update(_ask(template, attrs, allowed, short, batch, suffixes))
		except AIUnavailable as e:
			# Whatever earlier batches answered is still good; say so rather than silently mixing.
			# Not cached: a failure is a thing to retry, not an answer to keep for a day.
			done = " {0} variant(s) were read before it stopped.".format(len(values)) if values else ""
			return values, ("{0}.{1} Falling back to the built-in name matching - check the values "
							"before you continue.".format(e, done))

	frappe.cache().set_value(key, values, expires_in_sec=CACHE_TTL)
	return values, None
