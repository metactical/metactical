"""Legacy Storebuilder products: find them, prove they exist, then drop them after a merge.

A merge consolidates several legacy templates into one. On the Storebuilder side each of those
legacy templates is its own product, keyed by an **External ID** that must equal the ERP template
code, reachable at its own slug. ERPNext deletes the legacy templates during the merge
(`family.consolidate_templates`, `CustomItem.after_rename`), so after it has run there is nothing
left to tick *Drop and Create In Websites* on and the legacy product is stranded on the site -
live, orphaned, and a duplicate of the consolidated one.

So the slugs are collected and proven **before** the merge is queued, saved onto the job, and used
afterwards to issue the drops.

**Finding a slug** is optional help: `product_lookup_apis` on **Storebuilder Sync Settings** (an
`Item Import Validation` row per website, like every other Storebuilder API in this app) answers
`GET ?external_id=<item code>` with the product and its slug, and 404 when nothing maps to it. A
website with no row there is simply one where the operator types the slug in.

**Checking a slug** needs nothing configured at all: the storefront is asked for the page it points
at - `GET https://<Lead Source Domain>/<slug>`, the URL a person would paste into a browser. A 404
is a warning, not a refusal - a product already pulled from one site still has to be dropped from
the others, and a store behind a CDN can 404 anything that is not a browser.

The lookup key is the template item code and nothing else. item_code is mandatory, so it is always
populated, and it is the identity `websites.check` requires Storebuilder's External ID to equal.
(The other three Storebuilder callers in this app send `ifw_retailskusuffix or item_code`; that
disagreement is older than this module and is left alone here. A legacy product registered under a
retail SKU simply comes back 404 and falls through to manual entry.)

A snapshot is never good enough to authorise a deletion, which is why none of this goes through
Metabase the way `websites.py` does: every value here is read live from the site.
"""
import urllib.parse

import frappe
import requests
from frappe.utils import now_datetime

from metactical.item_merge import catalogue, family, websites

LOOKUP_FIELD = "product_lookup_apis"
DROP_DOCTYPE = "Item Drop and Create Log"
REGISTER = "Legacy Website Product"

# The two item.py callers of the slug endpoint pass no timeout at all, so a site that hangs holds
# the worker - or the user's form - open for as long as it likes. Same pair s3_image_api uses.
TIMEOUT = (5, 30)

# The slug check is a plain request to the storefront, so it is a browser asking, not an API client:
# a missing User-Agent is what a CDN blocks first.
REACH_TIMEOUT = (5, 15)
BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
			  "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")

# The lookup endpoint is new, so read its answer the way both Storebuilder response shapes already
# in this app are written rather than betting on one spelling.
SLUG_KEYS = ("slug", "Slug", "urlSlug", "UrlSlug")
EXTERNAL_ID_KEYS = ("externalId", "ExternalId", "external_id", "ExternalID")


# ---------- talking to the sites ----------

def _configs(parentfield):
	"""The per-website API rows, by price list.

	`enabled` is in the filter on purpose: the two item.py readers of item_detail_apis leave it out
	and go on calling rows somebody has switched off.
	"""
	rows = frappe.get_all("Item Import Validation", filters={"parentfield": parentfield, "enabled": 1},
						  fields=["*"])
	return {r.price_list: r for r in rows if r.price_list and r.api_url}


def _headers(config):
	"""The headers every Storebuilder caller in this app sends, written once.

	custom_header is a Password field, so it only comes back through get_password - a plain read
	returns asterisks. Resolve this on the request thread: it hits the database, and the callers
	below fan the requests out over a thread pool.
	"""
	headers = {"Content-Type": "application/json", "Authorization": "Bearer " + (config.api_key or "")}
	if config.get("custom_header"):
		secret = frappe.get_doc("Item Import Validation", config.name).get_password(
			"custom_header", raise_exception=False)
		if secret:
			headers["X-Origin-Verify"] = secret
	return headers


def _first(data, keys):
	for key in keys:
		value = data.get(key)
		if value not in (None, ""):
			return str(value).strip()
	return ""


def _product_of(data):
	"""The product in a response, or None when the site does not have one."""
	if not isinstance(data, dict):
		return None
	# Both spellings of "no such product" the sites use at HTTP 200.
	if data.get("Found") is False or data.get("found") is False:
		return None
	if data.get("error"):
		return None
	products = data.get("products") or data.get("Products")
	if isinstance(products, list):
		return products[0] if products else None
	return data


def _get(config, headers, param, value):
	url = "{0}{1}{2}={3}".format(config.api_url, "&" if "?" in config.api_url else "?", param,
								 urllib.parse.quote(str(value), safe=""))
	return requests.get(url, headers=headers, timeout=TIMEOUT)


def _lookup_one(config, headers, external_id):
	response = _get(config, headers, "external_id", external_id)
	if response.status_code == 404:
		return {"status": "not_mapped", "slug": "", "external_id": "",
				"note": "no Storebuilder product carries this External ID - type the slug in"}
	if response.status_code != 200:
		return {"status": "error", "slug": "", "external_id": "",
				"note": "the website returned HTTP {0}".format(response.status_code)}
	try:
		product = _product_of(response.json())
	except ValueError:
		return {"status": "error", "slug": "", "external_id": "",
				"note": "the website sent back a response we could not read"}
	if not product:
		return {"status": "not_mapped", "slug": "", "external_id": "",
				"note": "no Storebuilder product carries this External ID - type the slug in"}
	slug = _first(product, SLUG_KEYS)
	if not slug:
		return {"status": "error", "slug": "", "external_id": _first(product, EXTERNAL_ID_KEYS),
				"note": "the product is on the website but has no URL - type the slug in"}
	return {"status": "found", "slug": slug, "external_id": _first(product, EXTERNAL_ID_KEYS),
			"note": "found on the website"}


def page_url(domain, slug):
	"""The public product page a slug points at: https://<Lead Source Domain>/<slug>.

	The domain arrives already stripped of scheme, path and www by catalogue; the slug is a path,
	so the separators in it are left alone and only the characters that cannot go in one are escaped.
	"""
	path = urllib.parse.quote((slug or "").strip().strip("/"), safe="/-_~.")
	return "https://{0}/{1}".format(domain, path)


def _reach_one(url):
	"""Ask the website for the page. A 404 is the answer we are looking for, not an error."""
	try:
		response = requests.get(url, headers={"User-Agent": BROWSER_UA}, timeout=REACH_TIMEOUT,
								allow_redirects=True)
	except Exception as e:
		return {"reached": False, "status_code": None, "state": "unreachable",
				"note": "could not reach {0} ({1})".format(url, str(e)[:80])}

	code = response.status_code
	if code in (404, 410):
		return {"reached": False, "status_code": code, "state": "not_found",
				"note": "the website has no page at {0} (HTTP {1})".format(url, code)}
	if not 200 <= code < 300:
		return {"reached": False, "status_code": code, "state": "error",
				"note": "the website answered HTTP {0} for {1}".format(code, url)}

	# A store that redirects a dead slug to its homepage answers 200 for anything, so where we
	# landed matters as much as the code. Compare the **path** only: catalogue strips www from the
	# domain and these stores redirect the apex to www, so comparing whole URLs would call every
	# live page a redirect.
	asked = urllib.parse.urlparse(url).path.rstrip("/")
	landed_url = response.url or url
	landed = urllib.parse.urlparse(landed_url).path.rstrip("/")
	if landed != asked:
		return {"reached": False, "status_code": code, "state": "redirected",
				"note": "there is no page at {0} - it redirects to {1}".format(url, landed_url)}
	return {"reached": True, "status_code": code, "state": "live", "note": "the page is live at " + landed_url}


# ---------- what the page asks for ----------

def plan(products):
	"""One row per (legacy product, website), asking the websites nothing.

	This is the screen's starting point, so it must not depend on the lookup endpoint existing: an
	operator with no lookup API at all still gets the full grid and types the slugs in. Each row
	says what the websites are able to do for it, so the screen can offer the lookup where it works
	and stay out of the way where it does not.
	"""
	products = [str(p).strip() for p in (products or []) if str(p or "").strip()]
	storefronts = catalogue.storefronts()
	names = sorted(storefronts)
	lists = [s["price_list"] for s in storefronts.values() if s["price_list"]]
	lookups = _configs(LOOKUP_FIELD)

	# Which websites each legacy item was actually sold on. Not a rule - a product can be on a site
	# with no Item Price - but it is the difference between a row worth looking at and noise.
	priced = set()
	if products and lists:
		for row in frappe.get_all("Item Price", filters={"item_code": ["in", products],
														 "price_list": ["in", lists]},
								  fields=["item_code", "price_list"], distinct=True):
			priced.add((row.item_code, row.price_list))

	kept = saved(products)
	unpublished = not_published_items(products)

	rows = []
	for product in products:
		for lead_source in names:
			site = storefronts[lead_source]
			price_list = site["price_list"]
			row = kept.get((product, lead_source))
			rows.append({"product": product, "lead_source": lead_source, "price_list": price_list,
						 "site": site["domain"],
						 "slug": (row.slug if row else "") or "",
						 "source": (row.source if row else "") or "Manual",
						 "verified": int((row.verified if row else 0) or 0),
						 "state": (row.state if row else "") or "Not Checked",
						 "status": "saved" if row else "blank",
						 "note": (row.note if row else "") or "",
						 "has_item_price": (product, price_list) in priced,
						 "can_look_up": bool(price_list) and price_list in lookups,
						 "can_verify": bool(site["domain"])})

	done = covered(products)
	return {"products": products, "lead_sources": names, "price_lists": sorted(lists), "rows": rows,
			"any_lookup": bool(lookups),
			"any_verify": any(v["domain"] for v in storefronts.values()),
			"not_published": unpublished,
			"without_slug": sorted(p for p in products if p not in done)}


def lookup(products, lead_sources=None):
	"""One row per (legacy product, website): the slug the site has for that External ID.

	A website with no row is not an error and neither is a 404 - both just mean the operator has to
	supply the slug. A product with no slug on a website is left out of the drop entirely.
	"""
	products = [str(p).strip() for p in (products or []) if str(p or "").strip()]
	storefronts = catalogue.storefronts()
	names = sorted(storefronts) if lead_sources is None else [n for n in lead_sources if n in storefronts]
	configs = _configs(LOOKUP_FIELD)
	headers = {pl: _headers(config) for pl, config in configs.items()}  # on this thread: reads the DB

	rows, pending, calls = [], [], []
	for product in products:
		for lead_source in names:
			price_list = storefronts[lead_source]["price_list"]
			row = {"product": product, "lead_source": lead_source, "price_list": price_list,
				   "site": storefronts[lead_source]["domain"],
				   "external_id": product, "slug": "", "source": "Lookup", "status": "not_configured",
				   "note": "no product lookup API for this website - type the slug in, "
						   "or leave it blank to leave the site alone"}
			rows.append(row)
			config = configs.get(price_list) if price_list else None
			if config:
				pending.append(row)
				calls.append(lambda c=config, h=headers[price_list], e=product: _lookup_one(c, h, e))

	for row, (result, error) in zip(pending, websites._parallel(calls)):
		if error:
			row.update({"status": "error", "note": "could not reach the website: {0}".format(error)})
		else:
			row.update(result)
	return {"products": products, "lead_sources": names, "rows": rows}


def check(rows):
	"""Ask each website for the page its slug points at, in parallel. One entry per supplied row.

	This is a request to the storefront, not to an API: `https://<Lead Source Domain>/<slug>`, the
	same URL a person would paste into a browser to see whether the product is really there. It
	needs nothing configured beyond the domain already on the Lead Source, so it works on every
	website, which the old API check did not.
	"""
	rows = [r for r in (rows or []) if str(r.get("slug") or "").strip()]

	out, pending, calls = [], [], []
	for row in rows:
		lead_source = row.get("lead_source")
		site = catalogue.storefronts().get(lead_source) or {}
		domain, price_list = site.get("domain"), site.get("price_list")
		slug = str(row.get("slug")).strip()
		entry = {"product": row.get("product"), "lead_source": lead_source, "price_list": price_list,
				 "site": domain, "slug": slug, "source": row.get("source") or "Manual",
				 "url": page_url(domain, slug) if domain else None,
				 "status_code": None, "reached": False, "state": "no_domain",
				 "note": "this website has no domain set, so its pages cannot be checked"}
		if not price_list:
			# Not a warning: the drop message and its confirmation both key on the price list, so a
			# row here would be recorded and then never do anything.
			entry.update({"state": "no_price_list",
						  "note": "this website has no price list set, so a drop cannot be sent to it"})
		elif domain:
			pending.append(entry)
			calls.append(lambda u=entry["url"]: _reach_one(u))
		out.append(entry)

	for entry, (result, error) in zip(pending, websites._parallel(calls)):
		if error:
			entry.update({"reached": False, "state": "unreachable",
						  "note": "could not reach the website: {0}".format(error)})
		else:
			entry.update(result)
	return {"rows": out, "ok": all(r["reached"] for r in out)}


def claimed_elsewhere(pairs):
	"""{(Lead Source, slug): item code} for slugs some other legacy item has already claimed.

	One website, one slug, one item. Two items pointing at the same page would issue two drops for
	the same product: the second could never be confirmed, and whichever item is wrong takes a live
	product down with it.
	"""
	pairs = [(ls, slug) for ls, slug in (pairs or []) if ls and slug]
	if not pairs:
		return {}
	rows = frappe.get_all(
		"Legacy Website Product Slug",
		filters={"parenttype": REGISTER,
				 "lead_source": ["in", sorted({ls for ls, _ in pairs})],
				 "slug": ["in", sorted({slug for _, slug in pairs})]},
		fields=["parent", "lead_source", "slug"])
	wanted = set(pairs)
	return {(r.lead_source, r.slug): r.parent for r in rows if (r.lead_source, r.slug) in wanted}


def accept(rows):
	"""Sort what the operator supplied into what may be written, what is refused, and what to warn
	about. Returns {"keep", "refused", "problems", "warnings"}.

	Three things are refused outright, because writing them would do damage:
	  - a website nothing can be routed to (no price list) - see check();
	  - a slug the website has no page for, which would drop the wrong product or nothing at all;
	  - a slug another legacy item has already claimed on that website.

	Everything else is written. A website that could not answer - an error, an outage - warns
	instead: that is not the slug's fault, and a transient 503 must not stop the work.
	"""
	supplied = [r for r in (rows or []) if str(r.get("slug") or "").strip()]
	checked = {(r["product"], r["lead_source"], r["slug"]): r for r in check(supplied)["rows"]}
	claimed = claimed_elsewhere([(r.get("lead_source"), str(r.get("slug")).strip()) for r in supplied])

	# Two rows in one save can collide with each other before anything is written.
	within = {}
	for row in supplied:
		within.setdefault((row.get("lead_source"), str(row["slug"]).strip()), set()).add(row.get("product"))

	keep, refused, warnings = [], [], []
	for row in supplied:
		product, lead_source = row.get("product"), row.get("lead_source")
		slug = str(row["slug"]).strip()
		result = checked.get((product, lead_source, slug)) or {}

		def _refuse(note):
			refused.append({"product": product, "lead_source": lead_source, "slug": slug,
							"state": result.get("state"), "note": note})

		if result.get("state") == "no_price_list":
			_refuse(result.get("note"))
			continue

		if result.get("state") == "not_found":
			_refuse(result.get("note") or "the website has no page at that slug")
			continue

		owner = claimed.get((lead_source, slug))
		others = within.get((lead_source, slug), set()) - {product}
		if owner and owner != product:
			_refuse("{0} already has this slug on this website".format(owner))
			continue
		if others:
			_refuse("{0} is claiming the same slug on this website in this save".format(
				", ".join(sorted(others))))
			continue

		if not result.get("reached"):
			warnings.append("{0} on {1}: {2}".format(product, lead_source,
													 result.get("note") or "could not be checked"))

		keep.append({"product": product, "lead_source": lead_source,
					 "price_list": result.get("price_list"), "site": result.get("site"), "slug": slug,
					 "verified": int(bool(result.get("reached"))),
					 "state": result.get("state") or "no_domain",
					 "source": row.get("source") or "Manual",
					 "note": result.get("note") or ""})

	problems = ["{0} on {1}: {2}".format(r["product"], r["lead_source"], r["note"]) for r in refused]
	return {"keep": keep, "refused": refused, "problems": problems, "warnings": warnings}


# ---------- the register ----------
#
# One Legacy Website Product per item, one child row per website. An item on three websites is one
# record with three rows, not three records - so opening it shows the whole picture at once, and
# "has this item been dealt with" is answered by the record existing at all.

STATE_LABELS = {"live": "Live", "not_found": "Not Found", "redirected": "Redirected",
				"error": "Error", "unreachable": "Unreachable", "no_domain": "Not Checked"}


def records(products):
	"""The register records for these items, by item code."""
	products = [p for p in (products or []) if p]
	if not products:
		return {}
	names = frappe.get_all(REGISTER, filters={"item_code": ["in", products]}, pluck="name")
	return {doc.item_code: doc for doc in (frappe.get_doc(REGISTER, name) for name in names)}


def saved(products):
	"""Every recorded website row, flattened to {(item code, Lead Source): row}."""
	out = {}
	for item_code, doc in records(products).items():
		for row in doc.websites:
			out[(item_code, row.lead_source)] = row
	return out


def covered(products):
	"""The items somebody has already accounted for, with a slug or with Not Published.

	A record with no websites and no decision on it is not an answer, so it is not counted - and
	save() deletes one rather than leaving it behind to look like one.
	"""
	return {item_code for item_code, doc in records(products).items()
			if doc.status == "Not Published" or doc.websites}


def not_published_items(products):
	return sorted(item_code for item_code, doc in records(products).items()
				  if doc.status == "Not Published")


def _record_for(item_code, template=None):
	if frappe.db.exists(REGISTER, item_code):
		doc = frappe.get_doc(REGISTER, item_code)
		if template:
			doc.template = template
		return doc
	return frappe.get_doc({"doctype": REGISTER, "item_code": item_code, "template": template,
						   "status": "Captured"})


def _store(doc):
	"""Insert or update, whichever this record needs. The name is the item code, so it is known
	before the insert and `is_new` is the only thing that tells them apart."""
	if doc.get("__islocal") or not frappe.db.exists(REGISTER, doc.item_code):
		doc.insert(ignore_permissions=True)
	else:
		doc.save(ignore_permissions=True)


def not_published(item_code, on=True):
	"""Record, or undo, "this item has no Storebuilder product at all".

	Without it the block on Create variants would be impossible to satisfy for an item that was
	never on a website - and quietly letting those through would defeat the block.
	"""
	exists = frappe.db.exists(REGISTER, item_code)
	if on:
		doc = _record_for(item_code)
		doc.status = "Not Published"
		doc.websites = []
		_store(doc)
	elif exists:
		doc = frappe.get_doc(REGISTER, item_code)
		if doc.status == "Not Published":
			# It was only ever a decision, so undoing it leaves nothing to keep.
			frappe.delete_doc(REGISTER, item_code, ignore_permissions=True)
	frappe.db.commit()
	return {"item_code": item_code, "not_published": bool(on)}


def missing_slugs(template):
	"""Old variants of this template nobody has accounted for yet.

	This is what blocks Create variants: after the merge these items are gone, and a Storebuilder
	product nobody wrote a slug for can never be found again.
	"""
	# load_family hands back the variant docs as a list, in variant_codes order.
	_tdoc, docs, _stock, legacy = family.load_family(template)
	old = sorted(doc["name"] for doc in docs if not family.is_new(doc, legacy))
	if not old:
		return []
	done = covered(old)
	return [code for code in old if code not in done]


def save(template, rows):
	"""Check the operator's slugs and write them to the register, one record per item.

	Rows for an item replace that item's websites: the screen sends every website each time, so a
	row the operator deleted arrives as a blank slug and simply stops being written.

	A **refused** row is not the same as a deleted one and must not silently remove what was already
	there. The website it names keeps whatever it had - except when the refusal is that the slug
	already saved has since stopped resolving, where the row stays but is marked Not Found, so the
	record never claims a page is live when it is not.

	An item left with no websites at all has its record removed rather than kept as an empty one
	that would look like an answer.
	"""
	supplied = list(rows or [])
	verdict = accept(supplied)
	keep, refused = verdict["keep"], verdict["refused"]

	by_item = {}
	for row in supplied:
		by_item.setdefault(row.get("product"), [])
	for good in keep:
		by_item[good["product"]].append(good)

	refused_sites = {}
	for bad in refused:
		refused_sites.setdefault(bad["product"], {})[bad["lead_source"]] = bad

	written, removed = 0, 0
	for item_code, good_rows in by_item.items():
		existing = (frappe.get_doc(REGISTER, item_code) if frappe.db.exists(REGISTER, item_code)
					else None)
		was = {r.lead_source: r for r in existing.websites} if existing else {}
		held_back = _held_back(was, refused_sites.get(item_code, {}), [g["lead_source"] for g in good_rows])

		if not good_rows and not held_back:
			if existing and existing.status != "Not Published":
				frappe.delete_doc(REGISTER, item_code, ignore_permissions=True)
				removed += 1
			continue

		doc = _record_for(item_code, template)
		doc.status = "Captured"  # a product on a website means it was published after all
		doc.websites = []
		for good in good_rows:
			before = was.get(good["lead_source"])
			same = before and before.slug == good["slug"]
			doc.append("websites", {
				"lead_source": good["lead_source"], "slug": good["slug"], "source": good["source"],
				"state": STATE_LABELS.get(good["state"], "Not Checked"),
				"verified": good["verified"], "checked_on": now_datetime(), "note": good["note"],
				# A row that was already dropped keeps saying so.
				"status": (before.status if same else None) or "Captured",
				"drop_log": before.drop_log if same else None,
			})
		for row in held_back:
			doc.append("websites", row)
		_store(doc)
		written += len(good_rows)

	frappe.db.commit()
	return {"written": written, "removed": removed, "problems": verdict["problems"],
			"warnings": verdict["warnings"],
			"rows": [{"product": r["product"], "lead_source": r["lead_source"], "slug": r["slug"],
					  "verified": r["verified"], "state": r["state"], "source": r["source"],
					  "note": r["note"]} for r in keep]}


def _held_back(was, refusals, written_sites):
	"""The saved rows a refusal must not take down with it.

	A refused row leaves its website exactly as it was, so nothing is lost by a typo - except that a
	slug already on the record which has since stopped resolving is marked Not Found rather than
	left claiming to be live.
	"""
	out = []
	for lead_source, bad in refusals.items():
		before = was.get(lead_source)
		if not before or lead_source in written_sites:
			continue
		row = {f: before.get(f) for f in
			   ("lead_source", "price_list", "slug", "source", "verified", "state", "checked_on",
				"status", "drop_log", "note")}
		if bad.get("state") == "not_found" and before.slug == bad.get("slug"):
			row.update({"state": "Not Found", "verified": 0, "checked_on": now_datetime(),
						"note": bad.get("note")})
		out.append(row)
	return out


def for_products(products):
	"""The recorded rows for these items, as Item Merge Job Legacy Product rows."""
	out = []
	for item_code, doc in sorted(records(products).items()):
		if doc.status == "Not Published":
			continue
		for row in doc.websites:
			if row.slug and row.price_list:
				out.append({"product": item_code, "lead_source": row.lead_source,
							"price_list": row.price_list,
							"site": catalogue.storefront_domain(row.lead_source), "slug": row.slug,
							"source": row.source, "verified": row.verified, "state": row.state,
							"status": "Validated"})
	return out


def mark_dropped(item_code, lead_source, drop_log):
	"""Close the register row a drop was issued from, so the register says what happened."""
	if not frappe.db.exists(REGISTER, item_code):
		return
	doc = frappe.get_doc(REGISTER, item_code)
	for row in doc.websites:
		if row.lead_source == lead_source:
			row.db_set("status", "Dropped", update_modified=False)
			row.db_set("drop_log", drop_log, update_modified=False)
	if doc.websites and all(row.status == "Dropped" for row in doc.websites):
		frappe.db.set_value(REGISTER, item_code, "status", "Dropped", update_modified=False)


# ---------- after the merge ----------

def _still_owned(slug, price_list):
	"""The live Item, if any, that still publishes this slug on this website.

	The guard that matters: the website steps fill the surviving template's Item Detail rows from
	the Metabase snapshot just before this runs, and if the snapshot handed it a legacy product's
	slug then dropping that slug would delete the product the merge has just consolidated into.
	Anything still owned by a live Item is left alone and reported.
	"""
	parents = frappe.get_all("Item Detail", filters={"slug": slug, "price_list": price_list},
							 pluck="parent")
	for parent in parents:
		if parent and frappe.db.exists("Item", parent):
			return parent
	return None


def issue_drops(job, log=None):
	"""Create one Item Drop and Create Log per legacy (product, website) pair that has a slug.

	The existing drop webhook does the rest: it fires on the insert, publishes a DropProductMessage
	to the fanout exchange, and each site deletes the product matching the slug. `skip_recreate`
	stops the confirmation path pushing the product straight back.

	`product` is deliberately the **legacy** code, not the surviving template: the confirmation in
	item_rmq_api groups logs by product, so these stay a batch of their own and cannot be confused
	with a real drop and create on the survivor.

	The caller must have put the webhook flags back - see jobs.with_webhooks.
	"""
	from metactical.item_merge.jobs import _set_row  # deferred: jobs imports this module

	log = log or (lambda m: None)
	counts = {"issued": 0, "skipped": 0, "failed": 0}

	for row in job.get("legacy_products") or []:
		if row.status == "Issued":
			continue
		slug = (row.slug or "").strip()
		if not slug:
			_set_row(row, status="Skipped", message="no slug for this website")
			counts["skipped"] += 1
			continue

		# The row names a Lead Source, but the drop travels by price list: the fanout payload carries
		# it and receive_deletion_message matches the confirmation on it. A row that cannot resolve
		# one would be dropped into silence, so it fails here rather than looking like it worked.
		price_list = row.price_list or catalogue.price_list_for(row.lead_source)
		if not price_list:
			message = "{0} has no price list set, so a drop cannot be sent to it".format(row.lead_source)
			_set_row(row, status="Failed", message=message)
			log("legacy drop {0} {1}: FAILED - {2}".format(row.product, row.lead_source, message))
			counts["failed"] += 1
			continue

		owner = _still_owned(slug, price_list)
		if owner:
			message = "{0} still publishes this slug on {1} - not dropped".format(owner, row.lead_source)
			_set_row(row, status="Skipped", message=message)
			log("legacy drop {0} {1}: SKIPPED - {2}".format(row.product, row.lead_source, message))
			counts["skipped"] += 1
			continue

		try:
			drop = frappe.get_doc({
				"doctype": DROP_DOCTYPE,
				"product": row.product,
				# The legacy Item is gone by now, so its name is not available to put here.
				"item_name": row.product,
				"price_list": price_list,
				"slug": slug,
				"status": "Issued",
				"skip_recreate": 1,
			}).insert(ignore_permissions=True)
			frappe.db.commit()
		except Exception as e:
			frappe.db.rollback()
			frappe.log_error(title="Item Merge legacy drop {0}".format(row.product),
							 message=frappe.get_traceback())
			_set_row(row, status="Failed", message=str(e)[:1000])
			log("legacy drop {0} {1}: FAILED {2}".format(row.product, row.lead_source, str(e)[:300]))
			counts["failed"] += 1
			continue

		unproven = "" if row.verified else " - slug taken on the operator's word, this website could not check it"
		_set_row(row, status="Issued", drop_log=drop.name, message=None)
		mark_dropped(row.product, row.lead_source, drop.name)
		log("legacy drop {0} {1}: {2} issued ({3}){4}".format(row.product, row.lead_source, slug,
															  drop.name, unproven))
		counts["issued"] += 1

	return counts
