# Copyright (c) 2026, Storebuilder Commerce Inc and contributors
# For license information, please see license.txt

"""Item Merge Settings: what the merge carries between items, and where the website data comes from.

The Metabase half is the Item Merge page's only source of website information. The stand-alone app
kept the URL and key in app/.env.local and the per-site database ids in websites.py; on a bench they
belong on the same Single as the rest of the merge's configuration, where a System Manager can see
and change them.

Nothing asks Metabase while Enable Metabase is off.
"""

import frappe
import requests
from frappe import _
from frappe.model.document import Document

DEFAULT_TIMEOUT = 120


class NotConfigured(Exception):
	"""Metabase is off, or missing its URL, key or a database id - the caller reports it and stops."""


class ItemMergeSettings(Document):
	def validate(self):
		if self.metabase_url:
			self.metabase_url = self.metabase_url.strip().rstrip("/")
		seen = set()
		for row in self.metabase_databases or []:
			if row.price_list in seen:
				frappe.throw(_("Price list {0} is listed more than once").format(row.price_list))
			seen.add(row.price_list)
			if row.domain:
				row.domain = domain_of(row.domain)

	# ---------- reading the configuration ----------

	def check_ready(self):
		if not self.metabase_enabled:
			raise NotConfigured("Metabase is turned off in Item Merge Settings")
		if not self.metabase_url:
			raise NotConfigured("Item Merge Settings has no Metabase URL")
		if not self.get_password("metabase_api_key", raise_exception=False):
			raise NotConfigured("Item Merge Settings has no Metabase API key")

	def database_for(self, price_list):
		"""The Metabase database id for a price list's website, or None."""
		for row in self.metabase_databases or []:
			if row.enabled and row.price_list == price_list and row.database_id:
				return int(row.database_id)
		return None

	def domain_for(self, price_list):
		"""The website domain for a price list: the row's own, else its Lead Source's."""
		for row in self.metabase_databases or []:
			if row.price_list == price_list and row.domain:
				return row.domain
		domain = frappe.db.get_value("Lead Source", {"custom_neb_price_list": price_list}, "lead_source_domain")
		return domain_of(domain) or None

	# ---------- queries ----------

	def run_query(self, database_id, sql):
		"""One native read-only query. Returns a list of dicts, one per row.

		The snapshot databases are read replicas of the Storebuilder sites, so every query the Item
		Merge page sends is a SELECT; nothing here writes.
		"""
		self.check_ready()
		if not database_id:
			raise NotConfigured("No Metabase database id for that website")
		response = requests.post(
			f"{self.metabase_url}/api/dataset",
			json={"database": int(database_id), "type": "native", "native": {"query": sql}},
			headers={"Content-Type": "application/json",
					 "x-api-key": self.get_password("metabase_api_key", raise_exception=False)},
			timeout=(10, int(self.metabase_timeout or DEFAULT_TIMEOUT)),
		)
		if response.status_code != 200:
			raise RuntimeError(f"Metabase returned HTTP {response.status_code}")
		result = response.json()
		if result.get("error"):
			raise RuntimeError(f"Metabase: {result['error']}")
		data = result.get("data") or {}
		columns = [c["name"] for c in data.get("cols") or []]
		return [dict(zip(columns, row)) for row in data.get("rows") or []]


def domain_of(value):
	value = (value or "").lower().strip()
	value = value.split("://")[-1].split("/")[0]
	return value[4:] if value.startswith("www.") else value


def get_settings():
	"""The Single, whether or not Metabase is usable. Callers use check_ready()/database_for()."""
	return frappe.get_cached_doc("Item Merge Settings")


@frappe.whitelist()
def test_metabase_connection(database_id=None):
	"""Settings-form button: prove the URL, key and (optionally) one database id work."""
	frappe.only_for("System Manager")
	settings = frappe.get_doc("Item Merge Settings")
	try:
		settings.check_ready()
	except NotConfigured as e:
		frappe.throw(str(e), title=_("Metabase"))

	rows = settings.metabase_databases or []
	targets = [r for r in rows if str(r.database_id) == str(database_id)] if database_id \
		else [r for r in rows if r.enabled and r.database_id]
	if not targets:
		frappe.throw(_("Add at least one enabled site database row first"), title=_("Metabase"))

	out = []
	for row in targets:
		try:
			result = settings.run_query(row.database_id, "SELECT COUNT(*) AS Products FROM Products --")
			out.append({"price_list": row.price_list, "database_id": row.database_id, "ok": True,
						"products": (result[0] or {}).get("Products") if result else None})
		except Exception as e:
			out.append({"price_list": row.price_list, "database_id": row.database_id, "ok": False,
						"error": str(e)[:300]})
	return out
