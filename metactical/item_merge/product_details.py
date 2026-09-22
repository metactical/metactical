"""What Storebuilder holds for a template, asked in step 1 before anything is merged.

A merge consolidates several templates into one and ERPNext then deletes the losers. On the
Storebuilder side each of those templates is its own **product**, and once the ERP template is gone
there is nothing left to issue a drop from - the product is stranded on the site, live, a duplicate
of the consolidated one. So the handle on it, its **slug**, has to be captured while the templates
are still here: on the Find Template screen, before the operator leaves step 1.

`papi_product_details` answers with the whole product - `externalId`, `slug` and every variant - for
either an External ID or a slug:

    POST <site>/papi_product_details        {"externalId": "PROF1004"}
    POST <site>/papi_product_details        {"slug": "propper-mens-acu-trouser-battle-rip"}

**The External ID is asked for first** because it is the identity the drop relies on: Storebuilder's
External ID is meant to equal the ERP template item code. Only when that comes back empty is the
slug on the template's Item Detail row tried, and then the `externalId` the site hands back is
compared against the template code rather than trusted - the endpoint matches on more than the
External ID field (a request for `UF5505` answered with the product whose External ID is
`PROF1004`), so a hit is not by itself proof that the site has the item registered correctly.

**Which websites** a template is asked about: the price lists its family is actually priced on above
zero, kept to those whose Lead Source has a **Lead Source Domain** - `catalogue.storefronts()`, the
same definition the rest of item_merge uses for "a website there is". Templates on this catalogue
carry no Item Price of their own, so the variants' prices are what answer this.

Nothing here checks the storefront the way `legacy_products` used to. The answer comes from
Storebuilder itself, which is the system the drop is sent to, so there is nothing left to verify.
"""
import frappe
import requests
from frappe.utils import add_days, flt, format_datetime, now_datetime

from metactical.item_merge import catalogue, family, legacy_products, websites
from metactical.item_merge.rules import UserError

DETAIL_FIELD = "product_detail_apis"

# Three states, not two. `full` is an answer from Storebuilder. `nowebsite` and `zeroprice` are the
# absence of a question - nothing is priced there, so there is no product to drop and no price list
# on the row to take off with the ✕ either. Everything else needs attention.
#
# The distinction matters: counting "nothing to check" as "checked" is what made the screen report
# every template green when the site had no Item Prices at all.
CLEAN = "full"
NOTHING_TO_CHECK = ("nowebsite", "zeroprice")
SETTLED = (CLEAN,) + NOTHING_TO_CHECK

# A capture read from the register rather than from Storebuilder is only trusted for so long. Past
# this, the row asks to be checked again rather than opening the gate on a month-old answer.
CAPTURE_MAX_AGE_DAYS = 7


# ---------- talking to the sites ----------

def _post(config, headers, body):
	return requests.post(config.api_url, json=body, headers=headers, timeout=legacy_products.TIMEOUT)


def _ask(config, headers, body):
	"""One request. Returns (product, error message). Both may be None: no product, no fault."""
	try:
		response = _post(config, headers, body)
	except Exception as e:
		return None, "could not reach the website ({0})".format(str(e)[:80])
	if response.status_code == 404:
		return None, None
	if response.status_code != 200:
		return None, "the website returned HTTP {0}".format(response.status_code)
	try:
		return legacy_products._product_of(response.json()), None
	except ValueError:
		return None, "the website sent back a response we could not read"


def _grade(template, retail_sku, erp_slug, product, found_by):
	"""One website's answer, turned into a status the screen can colour and a message to act on."""
	external_id = legacy_products._first(product, legacy_products.EXTERNAL_ID_KEYS)
	slug = legacy_products._first(product, legacy_products.SLUG_KEYS) or erp_slug

	if not external_id:
		return {"status": "noexternalid", "external_id": "", "slug": slug,
				"message": "No External ID in Storebuilder - open this product in SB and set its "
						   "External ID to {0}".format(template)}

	if external_id != template:
		if retail_sku and external_id == retail_sku:
			message = ("Storebuilder is using the Retail SKU {0} as the External ID - it should be "
					   "the template code {1}".format(external_id, template))
		else:
			message = ("Storebuilder has the External ID {0} - it should be {1}".format(external_id,
																						template))
		return {"status": "wrongexternalid", "external_id": external_id, "slug": slug,
				"message": message}

	if not slug:
		return {"status": "noslug", "external_id": external_id, "slug": "",
				"message": "The product is on the website but has no URL - set its slug in Storebuilder"}

	return {"status": CLEAN, "external_id": external_id, "slug": slug,
			"message": "Item has full information (found by {0})".format(found_by)}


def _detail_one(config, headers, template, retail_sku, erp_slug):
	"""Ask one website about one template: External ID first, then the slug ERP has for it."""
	product, error = _ask(config, headers, {"externalId": template})
	if error:
		return {"status": "error", "external_id": "", "slug": "", "message": error}
	if product:
		return _grade(template, retail_sku, erp_slug, product, "External ID")

	if not erp_slug:
		return {"status": "noslug", "external_id": "", "slug": "",
				"message": "No Storebuilder product carries the External ID {0}, and there is no slug "
						   "on the Item Detail row for this price list to look it up with - add the "
						   "slug here, or set the External ID in Storebuilder".format(template)}

	product, error = _ask(config, headers, {"slug": erp_slug})
	if error:
		return {"status": "error", "external_id": "", "slug": "", "message": error}
	if product:
		return _grade(template, retail_sku, erp_slug, product, "slug")

	return {"status": "missing", "external_id": "", "slug": "",
			"message": "Can't find the item on this website - not by the External ID {0}, and not at "
					   "the slug {1}".format(template, erp_slug)}


# ---------- what a template is asked about ----------

def storefronts_by_price_list():
	"""{price list: Lead Source} for every storefront that has a Lead Source Domain.

	`catalogue.storefronts()` is already "every Lead Source with a domain set"; a storefront with no
	price list can be named but nothing can be routed to it - the drop message and its confirmation
	both key on the price list - so those are left out here.
	"""
	out = {}
	for lead_source, site in catalogue.storefronts().items():
		if site.get("price_list"):
			out[site["price_list"]] = lead_source
	return out


def priced_lists(codes, sites):
	"""({price list: row count} sold on, {price list: row count} priced only at zero).

	Sold on means **an Item Price above zero**. Templates on this catalogue carry no price of their
	own, so the variants are what answer this. The count is every row on that price list, zero-rate
	ones included, because that is what the ✕ would delete and what its warning has to say.

	A family priced entirely at zero on a website is reported separately rather than folded into
	"not sold anywhere": it *is* on that price list, and saying otherwise sends the operator looking
	for a missing price list that is not missing.

	`price_list_rate` carries a permlevel, so it is read through frappe.get_all rather than a
	permission-checked get_doc.
	"""
	if not codes or not sites:
		return {}, {}
	rows = frappe.get_all("Item Price",
						  filters={"item_code": ["in", codes], "price_list": ["in", sorted(sites)]},
						  fields=["price_list", "price_list_rate"])
	counts, sold = {}, set()
	for row in rows:
		counts[row.price_list] = counts.get(row.price_list, 0) + 1
		if flt(row.price_list_rate) > 0:
			sold.add(row.price_list)
	return ({pl: counts[pl] for pl in sorted(sold)},
			{pl: n for pl, n in sorted(counts.items()) if pl not in sold})


def _family_codes(template):
	return [template] + family.variant_codes(template)


def _erp_slugs(template):
	"""{price list: slug} from the template's Item Detail rows - the fallback lookup key."""
	rows = frappe.get_all("Item Detail", filters={"parent": template, "parenttype": "Item"},
						  fields=["price_list", "slug"])
	return {r.price_list: (r.slug or "").strip() for r in rows if r.price_list}


def _template_info(templates):
	"""{item code: {item_name, retail_sku}} - and the codes that are not templates are dropped."""
	if not templates:
		return {}
	rows = frappe.get_all("Item", filters={"name": ["in", templates]},
						  fields=["name", "item_name", "ifw_retailskusuffix"])
	return {r.name: {"item_name": r.item_name or "",
					 "retail_sku": (r.ifw_retailskusuffix or "").strip()} for r in rows}


def _rows_for(templates):
	"""The grid before anything is asked of the websites: one row per (template, price list).

	A template sold on no website at all still gets a row saying so - it is the answer to "why is
	nothing here" - but it is not a problem: there is no Storebuilder product to drop and no price
	list to take off the row, so there would be nothing for the operator to do about it.
	"""
	templates = [str(t).strip() for t in (templates or []) if str(t or "").strip()]
	sites = storefronts_by_price_list()
	configs = _configs()
	info = _template_info(templates)

	rows = []
	for template in templates:
		meta = info.get(template) or {"item_name": "", "retail_sku": ""}
		slugs = _erp_slugs(template)
		lists, zero = priced_lists(_family_codes(template), sites)

		def _blank(status, message, price_list=None, price_rows=0):
			lead_source = sites.get(price_list) if price_list else None
			return {"template": template, "item_name": meta["item_name"],
					"retail_sku": meta["retail_sku"], "price_list": price_list,
					"lead_source": lead_source,
					"site": catalogue.storefront_domain(lead_source) if lead_source else None,
					"external_id": "", "slug": "", "erp_slug": slugs.get(price_list, "") if price_list else "",
					"price_rows": price_rows, "can_look_up": False,
					"status": status, "message": message}

		# Priced at zero is not the same as not priced. Say which, and name the price list, so the
		# ✕ is there to take it off if it really is not sold on that site.
		for price_list, price_rows in zero.items():
			rows.append(_blank("zeroprice", "Priced at 0 on {0} - not treated as sold there, so "
									  "nothing is read from Storebuilder or dropped from it"
									  .format(price_list), price_list, price_rows))
		if not lists:
			if not zero:
				rows.append(_blank("nowebsite",
								   "Not sold on any website - no Item Price on a price list whose "
								   "Lead Source has a Lead Source Domain, so there is nothing on "
								   "Storebuilder to drop"))
			continue
		for price_list, price_rows in lists.items():
			lead_source = sites[price_list]
			rows.append({"template": template, "item_name": meta["item_name"],
						 "retail_sku": meta["retail_sku"], "price_list": price_list,
						 "lead_source": lead_source,
						 "site": catalogue.storefront_domain(lead_source),
						 "external_id": "", "slug": "", "erp_slug": slugs.get(price_list, ""),
						 "price_rows": price_rows, "can_look_up": price_list in configs,
						 "status": "notconfigured" if price_list not in configs else "",
						 "message": ("No Product Detail API for this price list - add one under "
									 "Product Detail APIs on Storebuilder Sync Settings")
									if price_list not in configs else ""})
	return rows, configs


def _configs():
	return legacy_products._configs(DETAIL_FIELD)


def _ok(rows):
	"""Nothing on the screen needs attention. **Not** the same as "everything was verified".

	A selection that is entirely "nothing to check" is ok to move on from - there is no product to
	drop and no price list on the row to take off - but nothing was read from Storebuilder either.
	Callers that want to say something reassuring have to look at `verified`, not at this.
	"""
	return bool(rows) and all(r["status"] in SETTLED for r in rows)


def _verified(rows):
	"""How many rows Storebuilder actually answered for."""
	return sum(1 for r in rows if r["status"] == CLEAN)


# ---------- what the page asks for ----------

def plan(templates):
	"""The grid, asking the websites nothing: what was captured last time, if anything.

	Opening step 1 must not fire a round of live calls at every site for every template the operator
	happens to tick, so this reads the register instead and leaves the asking to lookup().
	"""
	rows, configs = _rows_for(templates)
	kept = _saved_slugs({r["template"] for r in rows})
	cutoff = add_days(now_datetime(), -CAPTURE_MAX_AGE_DAYS)

	for row in rows:
		if row["status"] in NOTHING_TO_CHECK or row["status"] == "notconfigured":
			continue
		saved = kept.get((row["template"], row["lead_source"]))
		if not saved:
			row.update({"status": "unchecked", "message": "Not checked yet - press Check Storebuilder"})
			continue
		when = format_datetime(saved.checked_on) if saved.checked_on else "at some point"
		# Show what Storebuilder actually answered, not the item code we hoped it matched. Rows
		# captured before external_id was recorded have none, and say so rather than invent one.
		row.update({"external_id": saved.get("external_id") or "", "slug": saved.slug})
		if saved.checked_on and saved.checked_on < cutoff:
			row.update({"status": "stale",
						"message": "Captured {0}, more than {1} days ago - check it again before "
								   "relying on it".format(when, CAPTURE_MAX_AGE_DAYS)})
		else:
			row.update({"status": CLEAN, "message": "Captured {0}".format(when)})

	return {"templates": sorted({r["template"] for r in rows}), "rows": rows, "ok": _ok(rows),
			"verified": _verified(rows), "any_config": bool(configs), "checked_now": False}


def lookup(templates):
	"""Ask every website about every ticked template, in parallel. This is the live call."""
	rows, configs = _rows_for(templates)
	headers = {pl: legacy_products._headers(config) for pl, config in configs.items()}

	pending, calls = [], []
	for row in rows:
		# A row with nothing to check keeps what it says. A zero-priced one carries a price list, so
		# without this it would be looked up, come back `full`, and then be recorded and dropped for
		# a website the family is not sold on.
		if row["status"] in NOTHING_TO_CHECK:
			continue
		config = configs.get(row["price_list"]) if row["price_list"] else None
		if not config:
			continue  # notconfigured rows already say what is wrong
		pending.append(row)
		calls.append(lambda c=config, h=headers[row["price_list"]], t=row["template"],
							r=row["retail_sku"], s=row["erp_slug"]: _detail_one(c, h, t, r, s))

	for row, (result, error) in zip(pending, websites._parallel(calls)):
		if error:
			row.update({"status": "error", "external_id": "", "slug": "",
						"message": "could not reach the website: {0}".format(error)})
		else:
			row.update(result)

	return {"templates": sorted({r["template"] for r in rows}), "rows": rows, "ok": _ok(rows),
			"verified": _verified(rows), "checked_now": True}


# ---------- the register ----------

def _saved_slugs(templates):
	"""{(template code, Lead Source): row} already in the register."""
	out = {}
	for item_code, doc in legacy_products.records(sorted(templates)).items():
		for row in doc.websites:
			out[(item_code, row.lead_source)] = row
	return out


def save(survivor, rows, commit=True, under=None):
	"""Write what Storebuilder answered to the register, one record per consolidated-away template.

	This runs **before** the templates are consolidated, because consolidate_templates deletes them
	and the record is the only thing that outlives them. `template` is the survivor on every record,
	which is what jobs._legacy_rows reads the batch back by.

	**The survivor is never registered.** It is not a legacy product: the merge consolidates into it
	and its Storebuilder product is meant to stay and be updated. Registering it put it in the drop
	list and left it resting on `issue_drops._still_owned`, a guard that only holds when the
	survivor's Item Detail already carries that slug - which the website steps fill from Metabase,
	and which are skipped whenever Metabase is unreachable. A survivor with no Item Detail slug and
	no Metabase would have had its live product deleted.

	Returns {"written", "removed", "templates", "problems"}. A slug another item already claims is
	reported in `problems` rather than thrown: one bad row must not stop the rest being written, and
	it is something the operator can fix on the row.

	`commit=False` leaves the write in the caller's transaction, so a consolidation that fails
	afterwards rolls the register back with it instead of leaving records for a merge that never
	happened.

	`survivor` is the code the rows call the survivor - the one to leave out. `under` is the code to
	file the records against, which differs when the merge renames the survivor on its way through:
	the records have to name the code the job will look them up by, not the one being replaced.
	"""
	rows = rows or []
	survivor = str(survivor or "").strip()
	under = str(under or "").strip() or survivor

	# Every template on the screen, not only the ones with an answer: what is sent replaces what is
	# recorded, so a website the operator has since taken off the template with the ✕ has to stop
	# being recorded rather than sit there waiting to issue a drop for a site nothing is sold on.
	by_template = {str(r.get("template")): [] for r in rows if r.get("template")}
	for row in rows:
		if row.get("status") == CLEAN and str(row.get("slug") or "").strip():
			by_template[str(row["template"])].append(row)

	# One website, one slug, one item: two records pointing at the same page would issue two drops
	# for the same product. Caught here so it reads as a row problem, not a raw validation dialog.
	owners, problems = {}, []
	for template in sorted(by_template):
		if template == survivor:
			continue
		for row in by_template[template]:
			owners.setdefault((row.get("lead_source"), str(row["slug"]).strip()), set()).add(template)
	blocked = {key for key, templates in owners.items() if len(templates) > 1}
	for key in sorted(blocked):
		problems.append("{0} all point at {1} on {2} - only one item can own a page, so it was not "
						"recorded for any of them. Fix the External IDs in Storebuilder so each "
						"template finds its own product."
						.format(", ".join(sorted(owners[key])), key[1], key[0]))

	written, removed = 0, 0
	for template, good in sorted(by_template.items()):
		if template == survivor:
			# It survives, so it is not a legacy product. Clear any record an earlier save made
			# under a different survivor, or it stays in the drop list for ever.
			if frappe.db.get_value(legacy_products.REGISTER, template, "status") == "Captured":
				frappe.delete_doc(legacy_products.REGISTER, template, ignore_permissions=True)
				removed += 1
			continue

		good = [r for r in good
				if (r.get("lead_source"), str(r["slug"]).strip()) not in blocked]
		if not good:
			# Only a record still waiting to be dropped. One that has already been dropped, or that
			# somebody marked as never published, is history and is left alone.
			if frappe.db.get_value(legacy_products.REGISTER, template, "status") == "Captured":
				frappe.delete_doc(legacy_products.REGISTER, template, ignore_permissions=True)
				removed += 1
			continue

		doc = legacy_products._record_for(template, under)
		doc.status = "Captured"
		doc.websites = []
		for row in good:
			doc.append("websites", {
				"lead_source": row["lead_source"],
				"slug": str(row["slug"]).strip(),
				"external_id": row.get("external_id") or "",
				"source": "Lookup",
				"verified": 1,
				"state": "Live",
				"checked_on": now_datetime(),
				"note": row.get("message") or "found in Storebuilder",
			})
		try:
			legacy_products._store(doc)
		except Exception as e:
			problems.append("{0}: {1}".format(template, frappe.utils.strip_html(str(e))[:200]))
			continue
		written += len(good)

	if commit:
		frappe.db.commit()
	return {"written": written, "removed": removed, "templates": sorted(by_template),
			"problems": problems}


def ensure_captured(survivor, sources):
	"""Refuse a consolidation whose sources nobody captured. Raises UserError.

	The screen blocks this too, but the screen is a convenience - consolidate_templates is
	whitelisted and reachable without it, and once it has run the source templates are gone and
	their Storebuilder products can never be found again. This is the check that actually holds.
	"""
	sources = [str(c).strip() for c in (sources or []) if str(c or "").strip() and str(c).strip() != survivor]
	if not sources:
		return

	sites = storefronts_by_price_list()
	have = set(frappe.get_all(legacy_products.REGISTER,
							  filters={"item_code": ["in", sources]}, pluck="name"))
	missing = []
	for template in sources:
		if template in have:
			continue
		sold, _zero = priced_lists(_family_codes(template), sites)
		if sold:  # nothing recorded, and it is sold somewhere - that product would be stranded
			missing.append(template)
	if missing:
		raise UserError(
			"Storebuilder was never read for {0}: {1}. Open the Storebuilder products table under "
			"Find Template, press Check Storebuilder, and fix anything that is not green - once "
			"these templates are merged away their products can no longer be found."
			.format("{0} template(s)".format(len(missing)) if len(missing) > 1 else "one template",
					", ".join(sorted(missing)[:8])))


# ---------- taking a website off a template ----------

def remove_price_list(template, price_list):
	"""Delete every Item Price on this price list for the template and its variants.

	The way out for a template Storebuilder has nothing for: it is not sold on that website after
	all, so the row stops being asked about. Destructive and deliberate - the screen confirms it
	first, and unlike the rest of the Item Merge page this one runs with the outbound Webhooks left
	on, because it is a real catalogue change the websites have to hear about.
	"""
	template = str(template or "").strip()
	price_list = str(price_list or "").strip()
	if not (template and price_list):
		raise UserError("A template and a price list are both needed")

	# This deletes real prices with the website webhooks on, and it is whitelisted, so it checks
	# what it was handed rather than trusting the caller: a template, and a price list that is one
	# of the websites this screen is about.
	if not frappe.db.get_value("Item", template, "has_variants"):
		raise UserError("{0} is not a template".format(template))
	if price_list not in storefronts_by_price_list():
		raise UserError("{0} is not a website price list - its Lead Source has no Lead Source Domain"
						.format(price_list))

	names = frappe.get_all("Item Price",
						   filters={"item_code": ["in", _family_codes(template)],
									"price_list": price_list}, pluck="name")
	for name in names:
		frappe.delete_doc("Item Price", name, ignore_permissions=True)
	frappe.db.commit()

	family.add_activity(template, "removed {0} Item Price row(s) on {1}".format(len(names), price_list))
	return {"template": template, "price_list": price_list, "deleted": len(names)}
