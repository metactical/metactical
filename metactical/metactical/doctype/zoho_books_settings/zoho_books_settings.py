# Copyright (c) 2026, Metactical and contributors
# For license information, please see license.txt

import requests

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_to_date, get_datetime, nowdate, now_datetime

# Access tokens are valid for 1 hour; refresh a bit early to be safe.
TOKEN_EXPIRY_BUFFER_SECONDS = 120

# Per data center OAuth (accounts) and API domains. Most follow the
# zoho.{dc} pattern, but Canada uses zohocloud.ca for accounts.
DC_DOMAINS = {
	"com": ("https://accounts.zoho.com", "https://www.zohoapis.com"),
	"eu": ("https://accounts.zoho.eu", "https://www.zohoapis.eu"),
	"in": ("https://accounts.zoho.in", "https://www.zohoapis.in"),
	"com.au": ("https://accounts.zoho.com.au", "https://www.zohoapis.com.au"),
	"jp": ("https://accounts.zoho.jp", "https://www.zohoapis.jp"),
	"ca": ("https://accounts.zohocloud.ca", "https://www.zohoapis.ca"),
	"sa": ("https://accounts.zoho.sa", "https://www.zohoapis.sa"),
	"com.cn": ("https://accounts.zoho.com.cn", "https://www.zohoapis.com.cn"),
}


class ZohoBooksSettings(Document):
	def validate(self):
		self.set_domains()

	def set_domains(self):
		dc = (self.data_center or "com").strip()
		accounts, api = DC_DOMAINS.get(dc, (f"https://accounts.zoho.{dc}", f"https://www.zohoapis.{dc}"))
		self.accounts_domain = accounts
		# Re-derive api_domain from the map only when unset or the DC changed;
		# otherwise keep the authoritative value returned by Zoho's token response.
		if not self.api_domain or self.has_value_changed("data_center"):
			self.api_domain = api

	# ------------------------------------------------------------------
	# OAuth
	# ------------------------------------------------------------------
	def generate_tokens_from_code(self):
		"""Exchange the one-time grant token for refresh + access tokens."""
		if not self.authorization_code:
			frappe.throw(_("Please enter the Authorization Code (Grant Token) first."))

		self.set_domains()
		payload = {
			"grant_type": "authorization_code",
			"client_id": self.client_id,
			"client_secret": self.get_password("client_secret"),
			"code": self.authorization_code.strip(),
		}
		if self.redirect_uri:
			payload["redirect_uri"] = self.redirect_uri

		data = self._token_request(payload)
		if not data.get("refresh_token"):
			frappe.throw(
				_("Zoho did not return a refresh token. Grant tokens can only be used once — generate a new one. Response: {0}").format(
					frappe.as_json(data)
				)
			)

		self.refresh_token = data["refresh_token"]
		self._store_access_token(data)
		# The grant token is single-use; clear it so it is not reused by mistake.
		self.authorization_code = None
		self.save()
		return _("Tokens generated successfully.")

	def refresh_access_token(self):
		"""Use the refresh token to obtain a new access token."""
		if not self.refresh_token:
			frappe.throw(_("No refresh token available. Generate tokens first."))

		self.set_domains()
		payload = {
			"grant_type": "refresh_token",
			"client_id": self.client_id,
			"client_secret": self.get_password("client_secret"),
			"refresh_token": self.get_password("refresh_token"),
		}
		data = self._token_request(payload)
		self._store_access_token(data)
		self.save()

	def get_valid_access_token(self):
		"""Return a non-expired access token, refreshing if needed."""
		expiry = get_datetime(self.access_token_expiry) if self.access_token_expiry else None
		if not self.access_token or not expiry or expiry <= now_datetime():
			self.refresh_access_token()
		return self.get_password("access_token")

	def _log_error(self, title, url=None, payload=None, response=None, exception=None):
		"""Write a detailed entry to the Error Log for a failed Zoho request."""
		lines = [f"URL: {url}"]
		if payload is not None:
			lines.append(f"Params: {frappe.as_json(payload)}")
		if response is not None:
			lines.append(f"Status: {response.status_code}")
			lines.append(f"Response: {response.text[:2000]}")
		if exception is not None:
			lines.append(f"Exception: {exception}")
		lines.append(frappe.get_traceback())
		frappe.log_error(message="\n".join(lines), title=f"Zoho Books: {title}")

	def _token_request(self, payload):
		url = f"{self.accounts_domain}/oauth/v2/token"
		# Redact secrets before they can end up in any log.
		safe_payload = {k: v for k, v in payload.items() if k not in ("client_secret", "code", "refresh_token")}
		try:
			resp = requests.post(url, params=payload, timeout=30)
		except requests.RequestException as e:
			self._log_error("Zoho OAuth Request Failed", url=url, payload=safe_payload, exception=e)
			frappe.throw(_("Could not reach Zoho: {0}").format(e))

		try:
			data = resp.json()
		except ValueError:
			self._log_error("Zoho OAuth Bad Response", url=url, payload=safe_payload, response=resp)
			frappe.throw(_("Unexpected response from Zoho: {0}").format(resp.text))

		if resp.status_code != 200 or data.get("error"):
			self._log_error("Zoho OAuth Error", url=url, payload=safe_payload, response=resp)
			frappe.throw(_("Zoho OAuth error: {0}").format(data.get("error") or resp.text))
		return data

	def _store_access_token(self, data):
		self.access_token = data.get("access_token")
		expires_in = int(data.get("expires_in", 3600)) - TOKEN_EXPIRY_BUFFER_SECONDS
		self.access_token_expiry = add_to_date(now_datetime(), seconds=expires_in)
		# Zoho returns the authoritative API domain for this account; prefer it.
		if data.get("api_domain"):
			self.api_domain = data["api_domain"]

	# ------------------------------------------------------------------
	# API helper
	# ------------------------------------------------------------------
	def zoho_get(self, path, params=None):
		"""Perform an authenticated GET against the Zoho Books API."""
		if not self.organization_id:
			frappe.throw(_("Organization ID is required."))

		self.set_domains()
		params = dict(params or {})
		params["organization_id"] = self.organization_id
		headers = {"Authorization": f"Zoho-oauthtoken {self.get_valid_access_token()}"}
		url = f"{self.api_domain}/books/v3/{path.lstrip('/')}"

		try:
			resp = requests.get(url, headers=headers, params=params, timeout=60)
		except requests.RequestException as e:
			self._log_error("Zoho Books Request Failed", url=url, payload=params, exception=e)
			frappe.throw(_("Could not reach Zoho: {0}").format(e))

		try:
			data = resp.json()
		except ValueError:
			self._log_error("Zoho Books Bad Response", url=url, payload=params, response=resp)
			frappe.throw(_("Unexpected response from Zoho: {0}").format(resp.text))

		# code 0 means success in Zoho Books API
		if resp.status_code != 200 or data.get("code") not in (0, None):
			self._log_error("Zoho Books API Error", url=url, payload=params, response=resp)
			frappe.throw(_("Zoho Books API error: {0}").format(data.get("message") or resp.text))
		return data

	# ------------------------------------------------------------------
	# First run: credit cards -> native ERPNext Bank Account records
	# ------------------------------------------------------------------
	def fetch_credit_cards(self):
		"""Sync Zoho Books credit card accounts into ERPNext Bank Account records.

		Each Zoho account maps to a Bank Account, keyed by ``integration_id`` so
		re-runs update existing records instead of creating duplicates.
		"""
		# The bankaccounts endpoint only filters by Status; account_type is a
		# field on each record, so pull all accounts and filter here.
		data = self.zoho_get("bankaccounts", params={"filter_by": "Status.All"})
		accounts = [a for a in data.get("bankaccounts", []) if a.get("account_type") == "credit_card"]

		created = updated = 0
		for acc in accounts:
			if self._sync_bank_account(acc):
				created += 1
			else:
				updated += 1

		self.db_set("last_synced_on", now_datetime())
		return {"total": len(accounts), "created": created, "updated": updated}

	def _sync_bank_account(self, acc):
		"""Create or update a Bank Account for one Zoho card. Returns True if created."""
		account_id = acc.get("account_id")
		bank = _get_or_create_bank(acc.get("bank_name") or "Zoho Books")
		book_balance = acc.get("balance") or 0
		bank_balance = acc.get("bank_balance") or 0
		currency = acc.get("currency_code")
		values = {
			"account_name": acc.get("account_name") or account_id,
			"bank": bank,
			"account_type": _get_or_create_bank_account_type("Credit Card"),
			"bank_account_no": acc.get("account_number"),
			"integration_id": account_id,
			"last_integration_date": nowdate(),
			"disabled": 0 if acc.get("is_active") else 1,
			# Zoho custom fields
			"zoho_account_id": account_id,
			"zoho_account_code": acc.get("account_code"),
			"zoho_account_sub_type": acc.get("account_sub_type"),
			"zoho_currency": currency if frappe.db.exists("Currency", currency) else None,
			"zoho_book_balance": book_balance,
			"zoho_bank_balance": bank_balance,
			"zoho_balance_difference": bank_balance - book_balance,
			"zoho_uncategorized_transactions": acc.get("uncategorized_transactions") or 0,
			"zoho_feed_status": acc.get("feed_status"),
			"zoho_feeds_last_refresh_date": acc.get("feeds_last_refresh_date") or None,
			"zoho_last_synced_on": now_datetime(),
		}

		name = frappe.db.get_value("Bank Account", {"integration_id": account_id})
		if name:
			doc = frappe.get_doc("Bank Account", name)
			doc.update(values)
			doc.save()
			return False

		doc = frappe.get_doc({"doctype": "Bank Account", **values})
		doc.insert()
		return True


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _get_or_create_bank(bank_name):
	if frappe.db.exists("Bank", bank_name):
		return bank_name
	return frappe.get_doc({"doctype": "Bank", "bank_name": bank_name}).insert(ignore_permissions=True).name


def _get_or_create_bank_account_type(account_type):
	if frappe.db.exists("Bank Account Type", account_type):
		return account_type
	return frappe.get_doc(
		{"doctype": "Bank Account Type", "account_type": account_type}
	).insert(ignore_permissions=True).name


# ----------------------------------------------------------------------
# Whitelisted entry points (called from the client form)
# ----------------------------------------------------------------------
@frappe.whitelist()
def generate_tokens():
	doc = frappe.get_single("Zoho Books Settings")
	return doc.generate_tokens_from_code()


@frappe.whitelist()
def fetch_credit_cards():
	doc = frappe.get_single("Zoho Books Settings")
	result = doc.fetch_credit_cards()
	return _("Synced {total} credit card account(s): {created} created, {updated} updated.").format(**result)
