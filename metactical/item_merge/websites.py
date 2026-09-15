"""Website rows on a template: fill Item Detail (price list + slug) from the Storebuilder sites,
then check each site's product maps back to the template.

The sites are asked live through the same Storebuilder product API the image sync uses
(Storebuilder Sync Settings > Image APIs, one row per price list; see s3_image_api._fetch_sb_product).

Rules (agreed 2026-09-13):
  - check only the price lists in PRICE_LISTS, and only those the family has an Item Price on
  - a product counts as found when the site knows one of the family's product identities: the
	template code, the template's retail SKU, and every template code merged or renamed into the
	family (Item Merge History - including the old colour templates its variants came from)
  - found with a slug -> add the row (or fill an existing row's blank slug); never overwrite a slug
  - not found, found without a URL, or several different products found -> add nothing
  - then run "Load Data From SB" - but never while any row has a blank slug: get_item_details
	fills a blank-slug row with an unrelated product (seen on GOL1472, 2026-09-13)
  - a row Load Data From SB could not fill (no Item Detail API for that price list) gets the name and
	description from the product API, when it returns them; nothing already filled is overwritten
"""
import json
from concurrent.futures import ThreadPoolExecutor

import frappe
import requests

from metactical.item_merge import family

PRICE_LISTS = ["RET - Camo", "RET - CamoUSA", "RET - Gorilla", "RET - RAS", "RET - RASUSA"]
MAX_KEYS = 12
HTTP_WORKERS = 6


class NotConfigured(Exception):
	pass


# ---------- Storebuilder product API ----------

def site_configs():
	"""price list -> {api_url, headers, site} for the enabled Image API rows in PRICE_LISTS.

	Headers (and the encrypted custom header) are read here, on the request's own thread, so the
	lookups can then run side by side without touching the database."""
	rows = frappe.get_all("Item Import Validation", filters={"parentfield": "image_apis", "enabled": 1,
															 "price_list": ["in", PRICE_LISTS]}, fields=["*"])
	out = {}
	for row in rows:
		headers = {"Content-Type": "application/json", "Authorization": "Bearer " + (row.api_key or "")}
		if row.get("custom_header"):
			secret = frappe.get_doc("Item Import Validation", row.name).get_password("custom_header", raise_exception=False)
			if secret:
				headers["X-Origin-Verify"] = secret
		domain = frappe.db.get_value("Lead Source", {"custom_neb_price_list": row.price_list}, "lead_source_domain")
		out[row.price_list] = {"api_url": row.api_url, "headers": headers,
							   "site": domain or row.price_list.split("-")[-1].strip()}
	return out


def fetch_products(config, external_id, slug=None):
	"""Every product the site returns for this external id (and slug). No database access."""
	body = {"externalId": external_id}
	if slug:
		body["slug"] = slug.strip()
	response = requests.post(config["api_url"], json=body, headers=config["headers"], timeout=(5, 30))
	if response.status_code != 200:
		raise RuntimeError(f"{config['site']} returned HTTP {response.status_code}")
	data = response.json()
	return (data.get("products") or []) if data.get("found") else []


def _parallel(calls):
	if not calls:
		return []
	with ThreadPoolExecutor(max_workers=min(HTTP_WORKERS, len(calls))) as pool:
		futures = [pool.submit(c) for c in calls]
		out = []
		for f in futures:
			try:
				out.append((f.result(), None))
			except Exception as e:  # one unreachable site must not sink the others
				out.append((None, str(e) or e.__class__.__name__))
		return out


# ---------- the family's identities ----------

def family_keys(template):
	"""Product identities a site may know this family by, most likely first."""
	tdoc = frappe.db.get_value("Item", template, ["name", "ifw_retailskusuffix"], as_dict=True)
	codes = [template] + family.variant_codes(template)
	keys = [template] + ([tdoc.ifw_retailskusuffix] if tdoc and tdoc.ifw_retailskusuffix else [])
	# templates merged or renamed into this one, and the old templates its merged variants belonged to
	frontier, seen = set(codes), set(codes)
	for _ in range(4):
		rows = frappe.get_all("Item Merge History", filters={"new_item_code": ["in", list(frontier)]},
							  fields=["old_item_code", "old_item"])
		frontier = set()
		for r in rows:
			old = _json(r.old_item)
			if old.get("has_variants"):
				keys.append(r.old_item_code)
			if old.get("variant_of"):
				keys.append(old["variant_of"])
			if r.old_item_code not in seen:
				frontier.add(r.old_item_code)
				seen.add(r.old_item_code)
		if not frontier:
			break
	return [k for k in dict.fromkeys(keys) if k][:MAX_KEYS]


def _json(value):
	if isinstance(value, dict):
		return value
	try:
		return json.loads(value or "{}")
	except ValueError:
		return {}


# ---------- plan and apply ----------

def plan(template):
	"""What would be added. Reads only."""
	tdoc = family.load_template(template)
	configs = site_configs()
	if not configs:
		raise NotConfigured("No Storebuilder image API rows are enabled for " + ", ".join(PRICE_LISTS)
							+ " (Storebuilder Sync Settings > Image APIs)")
	codes = [template] + family.variant_codes(template)
	priced = set(frappe.get_all("Item Price", filters={"item_code": ["in", codes], "price_list": ["in", PRICE_LISTS]},
								pluck="price_list", distinct=True))
	rows = {r.get("price_list"): r for r in tdoc.get("item_detail") or []}
	keys = family_keys(template)

	out, lookups = [], []
	for pl in PRICE_LISTS:
		row = rows.get(pl)
		entry = {"price_list": pl, "has_item_price": pl in priced, "current_slug": (row or {}).get("slug") or None,
				 "row_exists": bool(row), "site": (configs.get(pl) or {}).get("site"), "found": None,
				 "slug": None, "action": "skip", "note": ""}
		out.append(entry)
		if pl not in priced:
			entry["note"] = "no Item Price on this price list"
		elif (entry["current_slug"] or "").strip():
			entry["note"] = "slug already set"
		elif pl not in configs:
			entry["note"] = "no Storebuilder API configured for this price list"
		else:
			lookups += [(entry, key) for key in keys]

	results = _parallel([(lambda e=e, k=k: fetch_products(configs[e["price_list"]], k)) for e, k in lookups])
	found = {}
	for (entry, key), (products, error) in zip(lookups, results):
		bucket = found.setdefault(entry["price_list"], {"products": {}, "errors": []})
		if error:
			bucket["errors"].append(error)
		for p in products or []:
			# the API unions its matches; keep only products that really carry one of our identities
			if (p.get("externalId") or "").strip().lower() == key.lower():
				bucket["products"][p.get("slug") or f"(no slug) {key}"] = p
	for entry in out:
		bucket = found.get(entry["price_list"])
		if not bucket:
			continue
		slugs = sorted({(p.get("slug") or "").strip() for p in bucket["products"].values()} - {""})
		entry["found"] = bool(bucket["products"])
		if not bucket["products"] and bucket["errors"]:
			entry["note"] = f"could not ask the site: {bucket['errors'][0]}"
		elif not bucket["products"]:
			entry["note"] = "not on the website"
		elif not slugs:
			entry["note"] = "on the website without a URL"
		elif len(slugs) > 1:
			entry["note"] = f"several products match: {', '.join(slugs)} - left for you"
		else:
			entry["slug"] = slugs[0]
			entry["action"] = "fill" if entry["row_exists"] else "add"
	return {"template": template, "keys": keys, "rows": out}


def apply(template, log=None):
	log = log or (lambda m: None)
	p = plan(template)
	todo = [r for r in p["rows"] if r["action"] in ("add", "fill")]
	doc = frappe.get_doc("Item", template)
	if todo:
		for t in todo:
			existing = next((r for r in doc.get("item_detail") or [] if r.price_list == t["price_list"]), None)
			if existing:
				existing.slug = t["slug"]
			else:
				doc.append("item_detail", {"price_list": t["price_list"], "slug": t["slug"]})
			log(f"{template}: {t['price_list']} slug {t['slug']} ({t['action']})")
		doc.save()
		frappe.db.commit()
		doc.reload()

	blank = [r.price_list for r in doc.get("item_detail") or [] if not (r.slug or "").strip()]
	if not doc.get("item_detail"):
		p["load_data_from_sb"] = "skipped: no website rows"
	elif blank:
		p["load_data_from_sb"] = f"skipped: blank slug on {', '.join(blank)} would load an unrelated product"
		log(f"{template}: Load Data From SB skipped - blank slug on {blank}")
	else:
		from metactical.custom_scripts.utils.s3_image_api import load_data_from_sb

		messages = load_data_from_sb(template) or []
		frappe.db.commit()
		p["load_data_from_sb"] = messages
		log(f"{template}: Load Data From SB -> " + " · ".join(frappe.utils.strip_html(m.get("message") or "") for m in messages)[:400])
	p["applied"] = todo
	p["filled_gaps"] = fill_gaps(template, log) if doc.get("item_detail") and not blank else []
	p["check"] = check(template)
	return p


def fill_gaps(template, log=None):
	"""Rows with a slug but no name and no description after Load Data From SB (e.g. CamoUSA: "No API
	setting found") take the product API's name and description, if it sends them."""
	log = log or (lambda m: None)
	doc = frappe.get_doc("Item", template)
	gaps = [r for r in doc.get("item_detail") or []
			if (r.slug or "").strip() and not (r.item_name or "").strip() and not (r.description or "").strip()]
	configs = site_configs() if gaps else {}
	calls = [(r, lambda c=configs[r.price_list], s=r.slug: fetch_products(c, template, s)) for r in gaps if r.price_list in configs]
	filled = []
	for (row, _), (products, error) in zip(calls, _parallel([c for _, c in calls])):
		prod = next((p for p in products or [] if (p.get("slug") or "").strip().lower() == row.slug.strip().lower()), None)
		name, description = (prod or {}).get("name"), (prod or {}).get("description")
		if error or not (name or description):
			continue
		row.item_name, row.description = name or "", description or ""
		filled.append(row.price_list)
		log(f"{template}: {row.price_list} name/description filled from the Storebuilder product API")
	if filled:
		doc.save()
		frappe.db.commit()
	return filled


# ---------- does each site's product map back to this template? ----------

def check(template):
	"""For every website row with a slug: the site's product for that slug, its External ID (must be
	the template code - Storebuilder maps variants through it) and its variant count against ERP's."""
	tdoc = family.load_template(template)
	kids = frappe.get_all("Item", filters={"variant_of": template}, fields=["name", "ifw_retailskusuffix"])
	erp_skus = {k.name for k in kids} | {k.ifw_retailskusuffix for k in kids if k.ifw_retailskusuffix}
	rows = [r for r in tdoc.get("item_detail") or [] if (r.get("slug") or "").strip()]
	configs = site_configs() if rows else {}

	calls, outs = [], []
	for r in rows:
		pl, slug = r.get("price_list"), r["slug"].strip()
		config = configs.get(pl)
		out = {"price_list": pl, "site": (config or {}).get("site"), "slug": slug, "external_id": None,
			   "external_id_match": None, "sb_variants": None, "erp_variants": len(kids), "count_match": None,
			   "unmatched_skus": [], "status": "", "note": ""}
		outs.append(out)
		if not config:
			out.update(status="skipped", note="no Storebuilder API configured for this price list")
			continue
		calls.append((out, lambda c=config, s=slug: fetch_products(c, template, s)))

	for (out, _), (products, error) in zip(calls, _parallel([c for _, c in calls])):
		slug = out["slug"]
		if error:
			out.update(status="error", note=f"could not ask the site: {error}")
			continue
		prod = next((p for p in products if (p.get("slug") or "").strip().lower() == slug.lower()), None)
		if not prod:
			out.update(status="notFound", note="the site has no product with this slug")
			continue
		variants = prod.get("variants") or []
		sb_skus = [v.get("fullRetailSku") or v.get("retailSkuSuffix") for v in variants]
		out.update(external_id=prod.get("externalId") or "", sb_variants=len(variants),
				   unmatched_skus=sorted(s for s in sb_skus if s and s not in erp_skus)[:20])
		out["external_id_match"] = out["external_id"].strip() == template
		out["count_match"] = len(variants) == len(kids)
		problems = []
		if not out["external_id_match"]:
			problems.append(f"External ID is '{out['external_id'] or '(blank)'}', not {template}")
		if not out["count_match"]:
			problems.append(f"{len(variants)} variant(s) on the site vs {len(kids)} in ERP")
		# a site variant SKU missing from ERP is shown for information; External ID and count decide
		out["status"] = "mismatch" if problems else "ok"
		out["note"] = " · ".join(problems)
	return {"template": template, "erp_variants": len(kids), "rows": outs,
			"ok": all(r["status"] in ("ok", "skipped") for r in outs)}
