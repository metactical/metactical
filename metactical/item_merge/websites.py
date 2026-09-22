"""Website rows on a template: fill Item Detail (price list + slug) from the Storebuilder sites,
then check each site's product maps back to the template.

**The source is Metabase.** Each site's Storebuilder database has a read-only snapshot there, and
this module queries it directly, the way the stand-alone app did. Credentials, the base URL and the
per-site database ids live on the **Item Merge Settings** Single; without them the website steps are
reported as needing setup and nothing is written.

A snapshot is refreshed irregularly - days, not hours - so every value read from one is reported
with the date of the copy it came from, and a mismatch found in a snapshot may already be fixed on
the live site.

Which price lists count is read from ERPNext (`catalogue.price_lists()`): every Lead Source that
names a `custom_neb_price_list`. It used to be a hard-coded list of five.

Rules (agreed 2026-09-13):
  - check only price lists that are configured websites, and only those the family has an Item Price on
  - a product counts as found when the snapshot knows any SKU the family has ever had: the template
	code, every variant code, their retail SKUs, and every code merged or renamed into them
  - found with a slug -> add the row (or fill an existing row's blank slug); never overwrite a slug
  - not found, found without a URL, or several different products found -> add nothing
  - then run "Load Data From SB" - but never while any row has a blank slug: get_item_details
	fills a blank-slug row with an unrelated product (seen on GOL1472, 2026-09-13)
  - a row Load Data From SB could not fill (no Item Detail API for that price list) takes the English
	name and description from the snapshot; nothing already filled is overwritten
"""
import json
from concurrent.futures import ThreadPoolExecutor

import frappe

from metactical.item_merge import catalogue, family

# A snapshot is searched on every SKU column at once, so the whole family fits in one query.
MAX_KEYS = 400
QUERY_WORKERS = 5


class NotConfigured(Exception):
	pass


def price_lists():
	return catalogue.price_lists()


def _parallel(calls):
	if not calls:
		return []
	with ThreadPoolExecutor(max_workers=min(QUERY_WORKERS, len(calls))) as pool:
		out = []
		for f in [pool.submit(c) for c in calls]:
			try:
				out.append((f.result(), None))
			except Exception as e:  # one unreachable site must not sink the others
				out.append((None, str(e) or e.__class__.__name__))
		return out


# ---------- Metabase ----------

def _sql_in(values):
	"""A SQL Server IN list of N'' literals, quotes doubled. Values are item codes and SKUs."""
	return ",".join("N'" + str(v).replace("'", "''") + "'" for v in values) or "N''"


def metabase():
	"""(settings, {price list: database id}). Raises NotConfigured when the Single is not usable.

	Read on the request's own thread so the queries afterwards can run side by side without touching
	the database. Imported lazily: the offline tests run against a stand-in frappe with no
	frappe.model, where the doctype controller is not importable.
	"""
	try:
		from metactical.metactical.doctype.item_merge_settings.item_merge_settings import get_settings
	except Exception as e:  # not migrated yet
		raise NotConfigured(f"Item Merge Settings is not available: {e}") from None
	settings = get_settings()
	try:
		settings.check_ready()
	except Exception as e:
		raise NotConfigured(str(e)) from None
	databases = {pl: settings.database_for(pl) for pl in price_lists() if settings.database_for(pl)}
	if not databases:
		raise NotConfigured("Item Merge Settings has no Metabase database id for "
							+ (", ".join(price_lists()) or "any price list"))
	return settings, databases


def snapshot_date(settings, database_id):
	"""The newest change in a site's snapshot, so everything read from it can be dated."""
	def build():
		try:
			rows = settings.run_query(database_id, """SELECT MAX(d) AS latest FROM (
  SELECT MAX(ModifiedOn) AS d FROM Products UNION ALL SELECT MAX(ModifiedOn) FROM ProductVariants) x --""")
		except Exception:
			return None
		return (str(rows[0].get("latest") or "")[:10] or None) if rows else None
	return catalogue.cached(("snapshot", database_id), build)


def _as_product(row, variants=None):
	return {"external_id": row.get("ExternalId") or "", "slug": (row.get("UrlSlug") or "").strip(),
			"sku": row.get("Sku"), "name": row.get("Name"), "description": row.get("Description"),
			"variants": variants if variants is not None else []}


def find_products(settings, database_id, keys):
	"""Live products in the snapshot carrying any of the family's SKUs.

	Every SKU column is searched, not just External ID, which is how a family that was never given an
	External ID is still found."""
	keys = list(keys)[:MAX_KEYS]
	if not keys:
		return []
	k = _sql_in(keys)
	rows = settings.run_query(database_id, f"""SELECT DISTINCT p.Id, p.ExternalId, p.Sku, p.UrlSlug, p.IsTrashed
FROM Products p LEFT JOIN ProductVariants v ON v.ProductId = p.Id
WHERE p.ExternalId IN ({k}) OR p.Sku IN ({k}) OR p.RetailSku IN ({k})
   OR v.FullSku IN ({k}) OR v.FullRetailSku IN ({k}) OR v.SkuSuffix IN ({k}) OR v.RetailSkuSuffix IN ({k}) --""")
	return [_as_product(r) for r in rows if not r.get("IsTrashed")]


def product_by_slug(settings, database_id, slug):
	"""Live products with this URL slug: External ID, English name and description, and variants."""
	q = _sql_in([slug])
	rows = settings.run_query(database_id, f"""SELECT p.Id, p.ExternalId, p.Sku, p.UrlSlug, t.Name, t.Description,
  (SELECT COUNT(*) FROM ProductVariants v WHERE v.ProductId = p.Id AND v.IsTrashed = 0) AS Variants,
  (SELECT STRING_AGG(COALESCE(NULLIF(v.FullRetailSku, ''), v.FullSku), '|') FROM ProductVariants v
    WHERE v.ProductId = p.Id AND v.IsTrashed = 0) AS VariantSkus
FROM Products p
LEFT JOIN ProductTranslations t ON t.ProductId = p.Id AND t.IsTrashed = 0
  AND t.LocaleId = (SELECT TOP 1 Id FROM Locales WHERE IsoCode = 'en')
WHERE p.UrlSlug = {q} AND p.IsTrashed = 0 --""")
	out = []
	for r in rows:
		skus = [s for s in str(r.get("VariantSkus") or "").split("|") if s]
		variants = [{"retail_sku": s} for s in skus]
		while len(variants) < int(r.get("Variants") or 0):  # the count is authoritative
			variants.append({})
		out.append(_as_product(r, variants))
	return out


# ---------- the family's identities ----------

def family_skus(template):
	"""Every SKU the family has ever been known by - template and variant codes, their retail SKUs,
	and every code merged or renamed into them."""
	kids = frappe.get_all("Item", filters={"variant_of": template}, fields=["name", "ifw_retailskusuffix"])
	tdoc = frappe.db.get_value("Item", template, ["name", "ifw_retailskusuffix"], as_dict=True) or {}
	keys = {template} | {k.name for k in kids}
	keys |= {k.ifw_retailskusuffix for k in kids if k.ifw_retailskusuffix}
	if tdoc.get("ifw_retailskusuffix"):
		keys.add(tdoc["ifw_retailskusuffix"])
	frontier = set(keys)
	for _ in range(4):
		if not frontier:
			break
		older = set(frappe.get_all("Item Merge History", filters={"new_item_code": ["in", list(frontier)]},
								   pluck="old_item_code"))
		frontier = older - keys
		keys |= frontier
	return sorted(k for k in keys if k)


# ---------- plan and apply ----------

def plan(template):
	"""What would be added. Reads only."""
	tdoc = family.load_template(template)
	settings, databases = metabase()
	lists = price_lists()
	codes = [template] + family.variant_codes(template)
	priced = set(frappe.get_all("Item Price", filters={"item_code": ["in", codes], "price_list": ["in", lists]},
								pluck="price_list", distinct=True)) if lists else set()
	rows = {r.get("price_list"): r for r in tdoc.get("item_detail") or []}
	keys = family_skus(template)

	out, wanted = [], []
	for pl in lists:
		row = rows.get(pl)
		entry = {"price_list": pl, "has_item_price": pl in priced, "current_slug": (row or {}).get("slug") or None,
				 "row_exists": bool(row), "site": catalogue.domain_for(pl), "found": None, "slug": None,
				 "action": "skip", "note": "", "as_of": None}
		out.append(entry)
		if pl not in priced:
			entry["note"] = "no Item Price on this price list"
		elif (entry["current_slug"] or "").strip():
			entry["note"] = "slug already set"
		elif pl not in databases:
			entry["note"] = "no Metabase database id for this website"
		else:
			wanted.append(entry)

	results = _parallel([(lambda e=e: find_products(settings, databases[e["price_list"]], keys)) for e in wanted])
	for entry, (products, error) in zip(wanted, results):
		entry["as_of"] = snapshot_date(settings, databases[entry["price_list"]])
		stale = f" (snapshot as of {entry['as_of']})" if entry["as_of"] else ""
		if error:
			entry["note"] = f"could not ask the snapshot: {error}"
			continue
		slugs = sorted({p["slug"] for p in products if p["slug"]})
		entry["found"] = bool(products)
		if not products:
			entry["note"] = "not on the website" + stale
		elif not slugs:
			entry["note"] = "on the website without a URL" + stale
		elif len(slugs) > 1:
			entry["note"] = f"several products match: {', '.join(slugs)} - left for you" + stale
		else:
			entry["slug"] = slugs[0]
			entry["action"] = "fill" if entry["row_exists"] else "add"
			entry["note"] = f"found in the snapshot as of {entry['as_of']}" if entry["as_of"] else "found"
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
			log(f"{template}: {t['price_list']} slug {t['slug']} ({t['action']})"
				+ (f" from the snapshot as of {t['as_of']}" if t.get("as_of") else ""))
		family.save_template(doc)  # never push the template's own fields onto its variants
		frappe.db.commit()
		doc.reload()

	blank = [r.price_list for r in doc.get("item_detail") or [] if not (r.slug or "").strip()]
	if not doc.get("item_detail"):
		p["load_data_from_sb"] = "skipped: no website rows"
	elif blank:
		p["load_data_from_sb"] = f"skipped: blank slug on {', '.join(blank)} would load an unrelated product"
		log(f"{template}: Load Data From SB skipped - blank slug on {blank}")
	else:
		# ERPNext's own action, not the product API: it refreshes each Item Detail row from its site
		from metactical.custom_scripts.utils.s3_image_api import load_data_from_sb

		messages = load_data_from_sb(template) or []
		frappe.db.commit()
		p["load_data_from_sb"] = messages
		log(f"{template}: Load Data From SB -> "
			+ " · ".join(frappe.utils.strip_html(m.get("message") or "") for m in messages)[:400])
	p["applied"] = todo
	p["filled_gaps"] = fill_gaps(template, log) if doc.get("item_detail") and not blank else []
	p["check"] = check(template)
	return p


def fill_gaps(template, log=None):
	"""Rows with a slug but no name and no description after Load Data From SB (e.g. CamoUSA: "No API
	setting found") take the English name and description from the snapshot."""
	log = log or (lambda m: None)
	doc = frappe.get_doc("Item", template)
	gaps = [r for r in doc.get("item_detail") or []
			if (r.slug or "").strip() and not (r.item_name or "").strip() and not (r.description or "").strip()]
	if not gaps:
		return []
	try:
		settings, databases = metabase()
	except NotConfigured:
		return []
	filled = []
	for row in gaps:
		if row.price_list not in databases:
			continue
		try:
			found = product_by_slug(settings, databases[row.price_list], row.slug.strip())
		except Exception:
			continue
		if len(found) != 1 or not (found[0]["name"] or found[0]["description"]):
			continue
		row.item_name = found[0]["name"] or ""
		row.description = found[0]["description"] or ""
		filled.append(row.price_list)
		log(f"{template}: {row.price_list} name/description filled from the snapshot "
			f"(as of {snapshot_date(settings, databases[row.price_list])})")
	if filled:
		family.save_template(doc)
		frappe.db.commit()
	return filled


# ---------- does each site's product map back to this template? ----------

def check(template):
	"""For every website row with a slug: the snapshot's product for that slug, its External ID (must
	be the template code - Storebuilder maps variants through it) and its variant count against ERP's."""
	tdoc = family.load_template(template)
	kids = frappe.get_all("Item", filters={"variant_of": template}, fields=["name", "ifw_retailskusuffix"])
	erp_skus = {k.name for k in kids} | {k.ifw_retailskusuffix for k in kids if k.ifw_retailskusuffix}
	rows = [r for r in tdoc.get("item_detail") or [] if (r.get("slug") or "").strip()]
	if not rows:
		return {"template": template, "erp_variants": len(kids), "rows": [], "ok": True}
	try:
		settings, databases = metabase()
	except NotConfigured as e:
		return {"template": template, "erp_variants": len(kids), "ok": True, "not_configured": str(e),
				"rows": [{"price_list": r.get("price_list"), "site": catalogue.domain_for(r.get("price_list")),
						  "slug": r["slug"].strip(), "external_id": None, "external_id_match": None,
						  "sb_variants": None, "erp_variants": len(kids), "count_match": None,
						  "unmatched_skus": [], "status": "skipped", "note": str(e), "as_of": None} for r in rows]}

	outs, calls = [], []
	for r in rows:
		pl, slug = r.get("price_list"), r["slug"].strip()
		out = {"price_list": pl, "site": catalogue.domain_for(pl), "slug": slug, "external_id": None,
			   "external_id_match": None, "sb_variants": None, "erp_variants": len(kids), "count_match": None,
			   "unmatched_skus": [], "status": "", "note": "", "as_of": None}
		outs.append(out)
		if pl not in databases:
			out.update(status="skipped", note="no Metabase database id for this website")
			continue
		calls.append((out, lambda db=databases[pl], s=slug: product_by_slug(settings, db, s)))

	for (out, _), (found, error) in zip(calls, _parallel([c for _, c in calls])):
		out["as_of"] = snapshot_date(settings, databases[out["price_list"]])
		stale = f" (snapshot as of {out['as_of']})" if out["as_of"] else ""
		if error:
			out.update(status="error", note=f"could not ask the snapshot: {error}")
			continue
		if not found:
			out.update(status="notFound", note=f"no live product with this slug{stale}")
			continue
		prod = found[0]
		sb_skus = [v.get("retail_sku") for v in prod["variants"]]
		out.update(external_id=prod["external_id"], sb_variants=len(prod["variants"]),
				   unmatched_skus=sorted(s for s in sb_skus if s and s not in erp_skus)[:20])
		out["external_id_match"] = out["external_id"].strip() == template
		out["count_match"] = len(prod["variants"]) == len(kids)
		problems = []
		if len(found) > 1:
			problems.append(f"{len(found)} live products use this slug")
		if not out["external_id_match"]:
			problems.append(f"External ID is '{out['external_id'] or '(blank)'}', not {template}")
		if not out["count_match"]:
			problems.append(f"{len(prod['variants'])} variant(s) on the site vs {len(kids)} in ERP")
		# a site variant SKU missing from ERP is shown for information; External ID and count decide
		out["status"] = "mismatch" if problems else "ok"
		out["note"] = " · ".join(problems) + (stale if problems else "")
	return {"template": template, "erp_variants": len(kids), "rows": outs,
			"ok": all(r["status"] in ("ok", "skipped") for r in outs)}
