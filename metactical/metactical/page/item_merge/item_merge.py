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

from metactical.item_merge import family, jobs, websites
from metactical.item_merge.rules import UserError

ROLES = ("System Manager", "Item Manager")


@contextmanager
def _api():
	frappe.only_for(ROLES)
	try:
		yield
	except (UserError, websites.NotConfigured) as e:
		frappe.db.rollback()
		frappe.throw(str(e), title=_("Item Merge"))


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
def check_consolidation(target, sources):
	with _api():
		return family.consolidation_check(target, _list(sources))


@frappe.whitelist()
def consolidate_templates(target, sources, rename_to=None, confirm_different_products=0):
	with _api():
		lines = []
		result = family.consolidate_templates(target, _list(sources), rename_to, cint(confirm_different_products), log=_logger(lines))
		family.add_activity(result["template"], "; ".join(lines))
		return result


@frappe.whitelist()
def rename_template(template, new_code=None, item_name=None):
	with _api():
		lines = []
		result = family.rename_template(template, new_code, item_name, log=_logger(lines))
		family.add_activity(result["template"], "; ".join(lines))
		return result


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
		return {"job": jobs.create_merge_job(template, _list(pairs), _list(leftovers), frappe.parse_json(options or "{}"))}


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
