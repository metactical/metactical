"""The things the merge used to hard-code, read from ERPNext instead.

The stand-alone app carried the five price lists, the deduct-qty Lead Source and the name of the
legacy attribute as literals, because it ran against one known site. In-process there is no reason
to guess: every one of them is already a record here, so ask.

Nothing in this module writes. Everything is cached per request - these are masters that change a
few times a year, and a merge job asks for them once per pair otherwise.
"""

import frappe

# Fallbacks used only when the site has nothing configured, so a bare test site still behaves.
DEFAULT_VARIANT_ATTRIBUTE = "Variant Number"


def _cache():
	"""Per-request memo. frappe.local is torn down between requests and between background jobs.

	Checked for None rather than with hasattr: frappe's own _dict answers any missing attribute with
	None instead of raising, so hasattr would say yes and getattr would hand back nothing.
	"""
	store = getattr(frappe.local, "_item_merge_catalogue", None)
	if store is None:
		store = {}
		frappe.local._item_merge_catalogue = store
	return store


def cached(key, build):
	store = _cache()
	if key not in store:
		store[key] = build()
	return store[key]


def clear():
	"""Forget the memo - after a Lead Source or Item Attribute changes, and in tests."""
	frappe.local._item_merge_catalogue = {}


# ---------- websites: price list <-> Lead Source ----------

def websites():
	"""{price list: {"lead_source":…, "domain":…}} for every Lead Source that names a price list.

	This is the definition of "a website we sell on" everywhere else in metactical - the Item Detail
	rows, the QOH deduct rows and the Storebuilder sync all key off custom_neb_price_list - so it is
	the right source for which price lists a merge should care about.
	"""
	def build():
		out = {}
		for row in frappe.get_all("Lead Source", filters={"custom_neb_price_list": ["is", "set"]},
								  fields=["name", "custom_neb_price_list", "lead_source_domain", "ais_report_label"]):
			domain = (row.lead_source_domain or row.ais_report_label or "").lower().strip()
			domain = domain.split("://")[-1].split("/")[0]
			out[row.custom_neb_price_list] = {"lead_source": row.name,
											  "domain": domain[4:] if domain.startswith("www.") else domain}
		return out
	return cached("websites", build)


def price_lists():
	"""The price lists a merge looks at, newest configuration first. Was a hard-coded list of five."""
	return sorted(websites())


def storefronts():
	"""{Lead Source: {"domain":…, "price_list":…}} for every Lead Source with a domain set.

	`websites()` above answers "which price lists does a merge touch", which is what the Item Detail
	rows and the sync key off. This answers "which websites are there", which is what an operator
	naming one actually picks. A storefront with no price list can be named but nothing can be
	routed to it - the drop message and its confirmation both key on the price list - so the caller
	has to say so rather than silently do nothing.
	"""
	def build():
		out = {}
		for row in frappe.get_all("Lead Source", filters={"lead_source_domain": ["is", "set"]},
								  fields=["name", "custom_neb_price_list", "lead_source_domain"]):
			domain = (row.lead_source_domain or "").lower().strip().split("://")[-1].split("/")[0]
			out[row.name] = {"domain": domain[4:] if domain.startswith("www.") else domain,
							 "price_list": row.custom_neb_price_list}
		return out
	return cached("storefronts", build)


def storefront_names():
	return sorted(storefronts())


def price_list_for(lead_source):
	return (storefronts().get(lead_source) or {}).get("price_list")


def storefront_domain(lead_source):
	return (storefronts().get(lead_source) or {}).get("domain")


def lead_source_for(price_list):
	return (websites().get(price_list) or {}).get("lead_source")


def domain_for(price_list):
	return (websites().get(price_list) or {}).get("domain")


# ---------- the deduct-qty Lead Source ----------

def deduct_lead_sources(item_code, template=None):
	"""Which website QOH deduct rows an item should carry, decided by where it actually sells.

	Was the literal "Website - Camo" on every merged item. A deduct row is what stops a website
	overselling, so it belongs on the sites the product is really listed on: the Lead Source of each
	price list the family has an Item Price on. A family with no prices yet falls back to the sites
	the template's Item Detail rows name, so a brand-new product still gets its row.
	"""
	codes = [c for c in {item_code, template} if c]
	if template:
		codes += frappe.get_all("Item", filters={"variant_of": template}, pluck="name")
	priced = set(frappe.get_all("Item Price", filters={"item_code": ["in", codes],
													   "price_list": ["in", price_lists()]},
								pluck="price_list", distinct=True)) if codes else set()
	if not priced and template:
		priced = {r.price_list for r in frappe.get_all("Item Detail", filters={"parent": template},
													   fields=["price_list"]) if r.price_list}
	return sorted({lead_source_for(pl) for pl in priced if lead_source_for(pl)})


# ---------- the legacy attribute being replaced ----------

def variant_attribute(template=None):
	"""The numeric Item Attribute the old variants hang off - "Variant Number" on this catalogue.

	Read rather than assumed: for a template, it is the numeric attribute that template carries, so a
	family using a differently named one still works. Falls back to the only numeric Item Attribute
	on the site, then to the conventional name.
	"""
	if template:
		rows = frappe.get_all("Item Variant Attribute", filters={"parent": template, "parenttype": "Item"},
							  fields=["attribute", "numeric_values"], order_by="idx asc")
		numeric = [r.attribute for r in rows if r.numeric_values]
		if numeric:
			return numeric[0]
	return site_variant_attribute()


def site_variant_attribute():
	def build():
		numeric = frappe.get_all("Item Attribute", filters={"numeric_values": 1}, pluck="name", order_by="name asc")
		if DEFAULT_VARIANT_ATTRIBUTE in numeric:
			return DEFAULT_VARIANT_ATTRIBUTE
		return numeric[0] if numeric else DEFAULT_VARIANT_ATTRIBUTE
	return cached("variant_attribute", build)
