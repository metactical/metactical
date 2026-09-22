"""Legacy Storebuilder products: keep the handle on them, then drop them after a merge.

A merge consolidates several templates into one. On the Storebuilder side each of those templates is
its own **product**, keyed by an **External ID** that must equal the ERP template code and reachable
at its own slug. ERPNext deletes the templates the merge consolidates away
(`family.consolidate_templates`, `CustomItem.after_rename`), so afterwards there is nothing left to
tick *Drop and Create In Websites* on and the legacy product is stranded on the site - live,
orphaned, and a duplicate of the consolidated one.

So the slugs are captured **before** anything is merged, on the Find Template screen, and kept here
until the job can issue the drops. The capturing is `product_details`, which asks
`papi_product_details` what each website holds for the template; this module is the register those
answers are written to and the drops that are issued from it.

One record per legacy template, one child row per website. A template on three websites is one
record with three rows, not three records - so opening it shows the whole picture at once, and "has
this template been dealt with" is answered by the record existing at all. `template` on the record
is the **surviving** code, which is how the merge job reads its batch back after the sources are
gone; the record's own name is the legacy code, which is what Storebuilder knows the product by.

A snapshot is never good enough to authorise a deletion, which is why none of this goes through
Metabase the way `websites.py` does: every value here was read live from the site.
"""
import frappe

from metactical.item_merge import catalogue

DROP_DOCTYPE = "Item Drop and Create Log"
REGISTER = "Legacy Website Product"

# The two item.py callers of the slug endpoint pass no timeout at all, so a site that hangs holds
# the worker - or the user's form - open for as long as it likes. Same pair s3_image_api uses.
TIMEOUT = (5, 30)

# Read Storebuilder's answer the way both response shapes already in this app are written rather
# than betting on one spelling.
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


# ---------- the register ----------

def records(products):
	"""The register records for these items, by item code."""
	products = [p for p in (products or []) if p]
	if not products:
		return {}
	names = frappe.get_all(REGISTER, filters={"item_code": ["in", products]}, pluck="name")
	return {doc.item_code: doc for doc in (frappe.get_doc(REGISTER, name) for name in names)}


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


def retarget(old_template, new_template):
	"""Follow a template rename. `template` is what jobs._legacy_rows reads the batch back by, and a
	rename after the capture would otherwise orphan every record it points at. The record names are
	left alone: those are the codes Storebuilder knows the legacy products by."""
	if not (old_template and new_template) or old_template == new_template:
		return 0
	names = frappe.get_all(REGISTER, filters={"template": old_template}, pluck="name")
	for name in names:
		frappe.db.set_value(REGISTER, name, "template", new_template, update_modified=False)
	return len(names)


def for_template(template):
	"""The recorded rows for a merge, as Item Merge Job Legacy Product rows.

	Read by the surviving template rather than by item code: by the time a merge is queued the
	templates this drops are already deleted, and the record is all that is left of them.

	Only **Captured** records: the surviving template keeps its record across merges, and the records
	of templates a previous merge already dropped stay under it too. Re-reading those would send a
	second drop for a product that is not there any more.
	"""
	out = []
	names = frappe.get_all(REGISTER, filters={"template": template, "status": "Captured"},
						   pluck="name")
	for name in sorted(names):
		doc = frappe.get_doc(REGISTER, name)
		for row in doc.websites:
			if row.slug and row.price_list:
				out.append({"product": doc.item_code, "lead_source": row.lead_source,
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
