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
from frappe.utils import flt, format_datetime, now_datetime

from metactical.item_merge import catalogue, family, legacy_products, websites

DETAIL_FIELD = "product_detail_apis"

# The statuses step 1 is allowed to move on from. `full` is an answer from Storebuilder; `nowebsite`
# is the absence of a question - a template nothing is priced on has no product to drop, and there
# would be no price list on the row to take off with the ✕ either, so treating it as a problem would
# be a dead end rather than something to fix.
CLEAN = "full"
SETTLED = (CLEAN, "nowebsite")


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
	"""{price list: how many Item Price rows the family has on it} for the websites it is sold on.

	Sold on means **an Item Price above zero**. Templates on this catalogue carry no price of their
	own, so the variants are what answer this. The count is every row on that price list, zero-rate
	ones included, because that is what the ✕ would delete and what its warning has to say.

	`price_list_rate` carries a permlevel, so it is read through frappe.get_all rather than a
	permission-checked get_doc.
	"""
	if not codes or not sites:
		return {}
	rows = frappe.get_all("Item Price",
						  filters={"item_code": ["in", codes], "price_list": ["in", sorted(sites)]},
						  fields=["price_list", "price_list_rate"])
	counts, sold = {}, set()
	for row in rows:
		counts[row.price_list] = counts.get(row.price_list, 0) + 1
		if flt(row.price_list_rate) > 0:
			sold.add(row.price_list)
	return {pl: counts[pl] for pl in sorted(sold)}


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
		lists = priced_lists(_family_codes(template), sites)
		if not lists:
			rows.append({"template": template, "item_name": meta["item_name"],
						 "retail_sku": meta["retail_sku"], "price_list": None, "lead_source": None,
						 "site": None, "external_id": "", "slug": "", "erp_slug": "",
						 "price_rows": 0, "can_look_up": False, "status": "nowebsite",
						 "message": "Not sold on any website - no price list above zero whose Lead "
									"Source has a Lead Source Domain, so there is nothing on "
									"Storebuilder to drop"})
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
	return bool(rows) and all(r["status"] in SETTLED for r in rows)


# ---------- what the page asks for ----------

def plan(templates):
	"""The grid, asking the websites nothing: what was captured last time, if anything.

	Opening step 1 must not fire a round of live calls at every site for every template the operator
	happens to tick, so this reads the register instead and leaves the asking to lookup().
	"""
	rows, configs = _rows_for(templates)
	kept = _saved_slugs({r["template"] for r in rows})

	for row in rows:
		if row["status"] in ("nowebsite", "notconfigured"):
			continue
		saved = kept.get((row["template"], row["lead_source"]))
		if saved:
			row.update({"external_id": row["template"], "slug": saved.slug, "status": CLEAN,
						"message": "Captured {0}".format(
							format_datetime(saved.checked_on) if saved.checked_on else "earlier")})
		else:
			row.update({"status": "unchecked", "message": "Not checked yet"})

	return {"templates": sorted({r["template"] for r in rows}), "rows": rows, "ok": _ok(rows),
			"any_config": bool(configs)}


def lookup(templates):
	"""Ask every website about every ticked template, in parallel. This is the live call."""
	rows, configs = _rows_for(templates)
	headers = {pl: legacy_products._headers(config) for pl, config in configs.items()}

	pending, calls = [], []
	for row in rows:
		config = configs.get(row["price_list"]) if row["price_list"] else None
		if not config:
			continue  # nowebsite and notconfigured rows already say what is wrong
		pending.append(row)
		calls.append(lambda c=config, h=headers[row["price_list"]], t=row["template"],
							r=row["retail_sku"], s=row["erp_slug"]: _detail_one(c, h, t, r, s))

	for row, (result, error) in zip(pending, websites._parallel(calls)):
		if error:
			row.update({"status": "error", "external_id": "", "slug": "",
						"message": "could not reach the website: {0}".format(error)})
		else:
			row.update(result)

	return {"templates": sorted({r["template"] for r in rows}), "rows": rows, "ok": _ok(rows)}


# ---------- the register ----------

def _saved_slugs(templates):
	"""{(template code, Lead Source): row} already in the register."""
	out = {}
	for item_code, doc in legacy_products.records(sorted(templates)).items():
		for row in doc.websites:
			out[(item_code, row.lead_source)] = row
	return out


def save(survivor, rows):
	"""Write what Storebuilder answered to the register, one record per template.

	This runs **before** the templates are consolidated, because consolidate_templates deletes them
	and the record is the only thing that outlives them. `template` is the survivor on every record,
	which is what jobs._legacy_rows reads the batch back by.

	The survivor is written along with the sources on purpose: it is one of the old products too, and
	issue_drops' `_still_owned` guard is what decides at drop time that its slug is still published
	by a live Item and leaves it alone.
	"""
	rows = rows or []
	# Every template on the screen, not only the ones with an answer: what is sent replaces what is
	# recorded, so a website the operator has since taken off the template with the ✕ has to stop
	# being recorded rather than sit there waiting to issue a drop for a site nothing is sold on.
	by_template = {str(r.get("template")): [] for r in rows if r.get("template")}
	for row in rows:
		if row.get("status") == CLEAN and str(row.get("slug") or "").strip():
			by_template[str(row["template"])].append(row)

	written, removed = 0, 0
	for template, good in sorted(by_template.items()):
		if not good:
			# Only a record still waiting to be dropped. One that has already been dropped, or that
			# somebody marked as never published, is history and is left alone.
			if frappe.db.get_value(legacy_products.REGISTER, template, "status") == "Captured":
				frappe.delete_doc(legacy_products.REGISTER, template, ignore_permissions=True)
				removed += 1
			continue
		doc = legacy_products._record_for(template, survivor)
		doc.status = "Captured"
		doc.websites = []
		for row in good:
			doc.append("websites", {
				"lead_source": row["lead_source"],
				"slug": str(row["slug"]).strip(),
				"source": "Lookup",
				"verified": 1,
				"state": "Live",
				"checked_on": now_datetime(),
				"note": row.get("message") or "found in Storebuilder",
			})
		legacy_products._store(doc)
		written += len(good)

	frappe.db.commit()
	return {"written": written, "removed": removed, "templates": sorted(by_template)}


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
		frappe.throw("A template and a price list are both needed")

	names = frappe.get_all("Item Price",
						   filters={"item_code": ["in", _family_codes(template)],
									"price_list": price_list}, pluck="name")
	for name in names:
		frappe.delete_doc("Item Price", name, ignore_permissions=True)
	frappe.db.commit()

	family.add_activity(template, "removed {0} Item Price row(s) on {1}".format(len(names), price_list))
	return {"template": template, "price_list": price_list, "deleted": len(names)}
