"""Item Merge page API: the whitelisted calls behind public/js/components/item_merge.

The page replaces the Variant Number attribute with real Item Attributes, one template family at a
time: find and merge templates -> create attribute variants -> line old variants up with new ones
-> merge them in a background job (Item Merge Job). The logic lives in metactical.item_merge; these
wrappers only check the role, parse the JSON arguments and turn a UserError into a message.
"""
from contextlib import contextmanager

import frappe
from frappe import _
from frappe.utils import cint

from metactical.item_merge import family, jobs, legacy_products, product_details, websites
from metactical.item_merge.rules import UserError

ROLES = ("System Manager", "Item Manager")
# Kept in step with the roles on item_merge.json, which decide who can open the page. Those only
# guard the desk route; every whitelisted method below is reachable by any logged-in user, so this
# is the real check - and most reads use frappe.get_all, which applies no permissions of its own.
ROLE_NEEDED = "Item Manager"

# No outbound Webhook may fire while a family is half restructured: on the server, Item alone
# carries three unconditional ones plus one on `doc.variant_of` - every variant save - and
# Item Price, Pricing Rule, Item Merge History and Item Group carry more. in_import is the first
# thing frappe's run_webhooks checks, so it returns before queueing anything. item_from_excel has
# to be set with it: CustomItem.validate clears in_import unless that flag is on, which would let
# every Item save through. The sites are updated once, deliberately, by the website steps at the
# end of the job. frappe.flags proxies frappe.local.flags, which is thread-local, so a concurrent
# request in this worker keeps its webhooks.
WEBHOOK_FLAGS = ("in_import", "item_from_excel")



@contextmanager
def _api(webhooks=False):
	"""Role check, a readable message for anything the user can fix, and no outbound Webhooks.

	The page restructures a catalogue in steps; pushing each half-finished step to the websites is
	never wanted. They are brought back in step by the website slugs step at the end of the job.

	`webhooks=True` leaves them alone. One call wants that: taking a price list off a template is not
	a half-finished restructuring step, it is a finished catalogue change the websites have to hear
	about, and the operator asked for it by name."""
	_require_roles()
	before = {name: frappe.local.flags.get(name) for name in WEBHOOK_FLAGS}
	for name in WEBHOOK_FLAGS:
		if not webhooks:
			frappe.local.flags[name] = True
	try:
		yield
	except (UserError, websites.NotConfigured) as e:
		frappe.db.rollback()
		frappe.throw(str(e), title=_("Item Merge"))
	finally:
		for name, value in before.items():
			frappe.local.flags[name] = value


def _require_roles():
	"""frappe.only_for raises a bare PermissionError, which reaches the browser as an empty dialog.
	Say what is missing and who can grant it instead."""
	try:
		frappe.only_for(ROLES)
	except frappe.PermissionError:
		frappe.throw(
			_("You need the {0} role to use Item Merge. Ask a System Manager to add it to your user.")
			.format(frappe.bold(_(ROLE_NEEDED))),
			frappe.PermissionError,
			title=_("Item Merge"),
		)


def _list(value):
	return frappe.parse_json(value) if isinstance(value, str) else (value or [])


def _logger(lines):
	return lines.append


# ---------- step 1: templates ----------

@frappe.whitelist()
def search_templates(sku=None, name=None):
	with _api():
		return {"templates": family.search_templates(sku, name)}


@frappe.whitelist()
def template_code_options(txt=None, **kwargs):
	"""Dropdown for the Template SKU box. Frappe's Autocomplete control posts `txt` and `query`."""
	with _api():
		return family.template_code_options(txt)


@frappe.whitelist()
def template_name_options(txt=None, **kwargs):
	"""Dropdown for the Template name box."""
	with _api():
		return family.template_name_options(txt)


@frappe.whitelist()
def check_consolidation(target, sources):
	with _api():
		return family.consolidation_check(target, _list(sources))


@frappe.whitelist()
def consolidate_templates(target, sources, rename_to=None, confirm_different_products=0,
						  product_rows=None):
	"""`product_rows` is the Storebuilder products table. It is recorded inside this call so a
	consolidation that fails takes the register write down with it."""
	with _api():
		lines = []
		result = family.consolidate_templates(target, _list(sources), rename_to,
											  cint(confirm_different_products),
											  product_rows=_list(product_rows), log=_logger(lines))
		family.add_activity(result["template"], "; ".join(lines))
		return result


@frappe.whitelist()
def rename_template(template, new_code=None, item_name=None):
	with _api():
		lines = []
		result = family.rename_template(template, new_code, item_name, log=_logger(lines))
		family.add_activity(result["template"], "; ".join(lines))
		return result


# ---------- step 1: the Storebuilder products behind the templates ----------

@frappe.whitelist()
def template_website_plan(templates):
	"""The grid under Find Template, asking the websites nothing - see product_details.plan."""
	with _api():
		return product_details.plan(_list(templates))


@frappe.whitelist()
def lookup_template_products(templates):
	"""Ask every website what it holds for these templates. Live papi_product_details calls."""
	with _api():
		return product_details.lookup(_list(templates))


@frappe.whitelist()
def save_template_products(survivor, rows):
	"""Write the captured External IDs and slugs to the Legacy Website Product register.

	Called before consolidate_templates, because that deletes the source templates and the register
	is the only thing that outlives them."""
	with _api():
		return product_details.save(survivor, _list(rows))


@frappe.whitelist()
def remove_template_price_list(template, price_list):
	"""Take a website off a template by deleting its Item Price rows.

	The one call on this page that runs with the outbound Webhooks left on: the sites have to be told
	the item is no longer priced for them."""
	with _api(webhooks=True):
		return product_details.remove_price_list(template, price_list)


# ---------- step 2: variants ----------

@frappe.whitelist()
def get_variants(template):
	with _api():
		return family.list_variants(template)


@frappe.whitelist()
def get_attribute_values(attribute):
	with _api():
		return {"attribute": attribute, "values": family.attribute_values(attribute)}


@frappe.whitelist()
def suggest_combinations(template, attributes):
	with _api():
		return family.suggest_combinations(template, _list(attributes))


@frappe.whitelist()
def create_variants(template, attributes, combinations, style_name=None, dry_run=0):
	with _api():
		# The websites were dealt with in step 1: the External ID and slug of every template this
		# merge consolidates away are already in the register, captured from Storebuilder before
		# anything was combined.
		return family.create_variants(template, _list(attributes), _list(combinations), style_name, cint(dry_run))


# ---------- step 3: align ----------

@frappe.whitelist()
def get_alignment(template):
	with _api():
		return family.alignment(template)


@frappe.whitelist()
def check_alignment(template, pairs, leftovers=None):
	with _api():
		return family.check_plan(template, _list(pairs), _list(leftovers))


@frappe.whitelist()
def fix_settings(template, pairs):
	with _api():
		lines = []
		result = family.fix_settings(template, _list(pairs), log=_logger(lines))
		if lines:
			family.add_activity(template, "; ".join(lines))
		return result


# ---------- step 4: jobs ----------

@frappe.whitelist()
def queue_merge(template, pairs, leftovers=None, options=None):
	with _api():
		return {"job": jobs.create_merge_job(template, _list(pairs), _list(leftovers),
											 frappe.parse_json(options or "{}"))}


@frappe.whitelist()
def queue_item_changes(template, changes):
	with _api():
		return {"job": jobs.create_changes_job(template, _list(changes))}


@frappe.whitelist()
def list_jobs(template=None):
	with _api():
		return {"jobs": jobs.list_jobs(template)}


@frappe.whitelist()
def get_job(job, live=1):
	with _api():
		return jobs.job_status(job, cint(live))


@frappe.whitelist()
def resume_job(job):
	with _api():
		return {"job": jobs.resume(job)}


@frappe.whitelist()
def get_reposts(template):
	with _api():
		return family.reposts(template)


# ---------- websites ----------

@frappe.whitelist()
def get_website_plan(template):
	with _api():
		return websites.plan(template)


@frappe.whitelist()
def apply_websites(template):
	with _api():
		lines = []
		result = websites.apply(template, log=_logger(lines))
		if lines:
			family.add_activity(template, "; ".join(lines))
		return result


@frappe.whitelist()
def check_websites(template):
	with _api():
		return websites.check(template)


# ---------- legacy website products ----------

@frappe.whitelist()
def legacy_drop_plan(template):
	"""What this merge will drop from the websites: the register rows step 1 captured. Reads only."""
	with _api():
		return {"template": template, "rows": legacy_products.for_template(template)}
