# Copyright (c) 2026, Storebuilder Commerce Inc and contributors
# For license information, please see license.txt

import base64
import secrets
import urllib.parse

import requests

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_to_date, get_datetime, now_datetime

AUTH_BASE_URL = "https://appcenter.intuit.com/connect/oauth2"
TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
API_BASE_URLS = {
    "production": "https://quickbooks.api.intuit.com",
    "sandbox": "https://sandbox-quickbooks.api.intuit.com",
}
SCOPES = "com.intuit.quickbooks.accounting"
MINOR_VERSION = "75"
ACCESS_TOKEN_BUFFER_SECONDS = 120


class QBOSettings(Document):
    @property
    def api_base_url(self):
        return API_BASE_URLS.get(self.environment or "production")

    # ------------------------------------------------------------------
    # OAuth — step 1: generate authorization URL
    # ------------------------------------------------------------------
    def get_authorization_url(self):
        if not self.client_id:
            frappe.throw(_("Client ID is required."))
        if not self.redirect_uri:
            frappe.throw(_("Redirect URI is required."))

        state = secrets.token_urlsafe(16)
        frappe.cache().set_value("qbo_oauth_state", state, expires_in_sec=600)

        query = urllib.parse.urlencode({
            "client_id": self.client_id,
            "response_type": "code",
            "scope": SCOPES,
            "redirect_uri": self.redirect_uri,
            "state": state,
        })
        return f"{AUTH_BASE_URL}?{query}"

    # ------------------------------------------------------------------
    # OAuth — step 2: exchange code for tokens (called from the callback page)
    # ------------------------------------------------------------------
    def exchange_code_for_tokens(self, code, realm_id, state):
        expected = frappe.cache().get_value("qbo_oauth_state")
        if not expected or state != expected:
            frappe.throw(_("OAuth state mismatch — possible CSRF attempt."))
        frappe.cache().delete_value("qbo_oauth_state")

        data = self._token_request({
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
        })
        self._store_tokens(data, realm_id=realm_id)
        self.connection_status = "Connected"
        self.connected_at = now_datetime()
        self.save(ignore_permissions=True)

    # ------------------------------------------------------------------
    # OAuth — token refresh
    # ------------------------------------------------------------------
    def refresh_access_token(self):
        if not self.refresh_token:
            frappe.throw(_("No refresh token — please reconnect to QuickBooks."))

        data = self._token_request({
            "grant_type": "refresh_token",
            "refresh_token": self.get_password("refresh_token"),
        })
        self._store_tokens(data)
        self.save(ignore_permissions=True)

    def get_valid_access_token(self):
        if not self.access_token:
            frappe.throw(_("No access token — connect via OAuth or paste a token from the API Playground."))

        # If expiry is set and the token has expired, refresh. If expiry is blank
        # (token pasted manually from the Playground), use it as-is and let a 401
        # trigger an explicit refresh later.
        if self.access_token_expiry and get_datetime(self.access_token_expiry) <= now_datetime():
            self.refresh_access_token()

        return self.get_password("access_token")

    # ------------------------------------------------------------------
    # Disconnect
    # ------------------------------------------------------------------
    def clear_tokens(self):
        self.realm_id = None
        self.access_token = None
        self.refresh_token = None
        self.access_token_expiry = None
        self.refresh_token_expiry = None
        self.connection_status = "Disconnected"
        self.connected_at = None
        self.save(ignore_permissions=True)

    # ------------------------------------------------------------------
    # QBO API helpers
    # ------------------------------------------------------------------
    def qbo_get(self, path, params=None):
        """Authenticated GET against the QBO REST API."""
        if not self.realm_id:
            frappe.throw(_("Not connected to QuickBooks."))

        url = f"{self.api_base_url}/v3/company/{self.realm_id}/{path.lstrip('/')}"
        params = dict(params or {})
        params.setdefault("minorversion", MINOR_VERSION)
        headers = {
            "Authorization": f"Bearer {self.get_valid_access_token()}",
            "Accept": "application/json",
        }

        try:
            resp = requests.get(url, headers=headers, params=params, timeout=60)
        except requests.RequestException as e:
            frappe.log_error(str(e), "QBO GET Failed")
            frappe.throw(_("Could not reach QuickBooks: {0}").format(e))

        if resp.status_code == 401:
            self.refresh_access_token()
            headers["Authorization"] = f"Bearer {self.get_password('access_token')}"
            resp = requests.get(url, headers=headers, params=params, timeout=60)

        resp.raise_for_status()
        return resp.json()

    def qbo_query(self, statement):
        """Run a QBO SQL-like query, e.g. 'SELECT * FROM Bill MAXRESULTS 100'."""
        if not self.realm_id:
            frappe.throw(_("Not connected to QuickBooks."))

        url = f"{self.api_base_url}/v3/company/{self.realm_id}/query"
        headers = {
            "Authorization": f"Bearer {self.get_valid_access_token()}",
            "Accept": "application/json",
        }
        params = {"query": statement, "minorversion": MINOR_VERSION}

        try:
            resp = requests.get(url, headers=headers, params=params, timeout=60)
        except requests.RequestException as e:
            frappe.log_error(str(e), "QBO Query Failed")
            frappe.throw(_("Could not reach QuickBooks: {0}").format(e))

        if resp.status_code == 401:
            self.refresh_access_token()
            headers["Authorization"] = f"Bearer {self.get_password('access_token')}"
            resp = requests.get(url, headers=headers, params=params, timeout=60)

        resp.raise_for_status()
        return resp.json().get("QueryResponse", {})

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------
    def _basic_auth_header(self):
        raw = f"{self.client_id}:{self.get_password('client_secret')}".encode()
        return "Basic " + base64.b64encode(raw).decode()

    def _token_request(self, payload):
        try:
            resp = requests.post(
                TOKEN_URL,
                headers={
                    "Authorization": self._basic_auth_header(),
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data=payload,
                timeout=30,
            )
        except requests.RequestException as e:
            frappe.log_error(str(e), "QBO Token Request Failed")
            frappe.throw(_("Could not reach Intuit: {0}").format(e))

        if not resp.ok:
            frappe.log_error(resp.text[:2000], "QBO Token Error")
            frappe.throw(_("Intuit OAuth error: {0}").format(resp.text[:500]))

        return resp.json()

    def _store_tokens(self, data, realm_id=None):
        now = now_datetime()
        self.access_token = data["access_token"]
        self.refresh_token = data["refresh_token"]
        expires_in = int(data.get("expires_in", 3600)) - ACCESS_TOKEN_BUFFER_SECONDS
        self.access_token_expiry = add_to_date(now, seconds=expires_in)
        refresh_expires_in = int(data.get("x_refresh_token_expires_in", 8640000))
        self.refresh_token_expiry = add_to_date(now, seconds=refresh_expires_in)
        if realm_id:
            self.realm_id = realm_id


    # ------------------------------------------------------------------
    # Bank Accounts
    # ------------------------------------------------------------------
    def fetch_bank_accounts(self):
        """Pull QBO Account records (type Bank/Credit Card) and upsert ERPNext Bank Accounts."""
        page_size = 100
        start = 1
        created = updated = 0

        while True:
            stmt = (
                f"SELECT * FROM Account WHERE AccountType IN ('Bank', 'Credit Card')"
                f" STARTPOSITION {start} MAXRESULTS {page_size}"
            )
            body = self.qbo_query(stmt)
            batch = body.get("Account", [])
            if not batch:
                break

            for acct in batch:
                if self._sync_bank_account(acct):
                    created += 1
                else:
                    updated += 1

            if len(batch) < page_size:
                break
            start += page_size

        self.db_set("bank_accts_last_synced", now_datetime())

        from metactical.metactical.doctype.qbo_sync_log.qbo_sync_log import log_sync
        log_sync(
            operation="Bank Accounts",
            status="Success",
            records_processed=created + updated,
            records_created=created,
            records_updated=updated,
        )
        return {"created": created, "updated": updated}

    def _sync_bank_account(self, acct):
        """Upsert one ERPNext Bank Account. Returns True if created, False if updated."""
        qbo_id = str(acct.get("Id") or "")
        if not qbo_id:
            return False

        account_name = acct.get("Name") or qbo_id
        bank_name = _get_or_create_bank("QuickBooks")
        company = self.default_company or frappe.db.get_single_value("Global Defaults", "default_company")

        values = {
            "account_name": account_name,
            "bank": bank_name,
            "bank_account_no": acct.get("AcctNum") or None,
            "integration_id": qbo_id,
            "last_integration_date": frappe.utils.nowdate(),
            "company": company,
            "disabled": 0 if acct.get("Active", True) else 1,
        }

        existing = frappe.db.get_value("Bank Account", {"integration_id": qbo_id})
        if existing:
            doc = frappe.get_doc("Bank Account", existing)
            doc.update(values)
            doc.save(ignore_permissions=True)
            return False

        frappe.get_doc({"doctype": "Bank Account", **values}).insert(ignore_permissions=True)
        return True

    # ------------------------------------------------------------------
    # Bank Transactions
    # ------------------------------------------------------------------
    def fetch_bank_transactions(self):
        """Pull QBO Purchase + Deposit records and create ERPNext Bank Transaction docs.

        QBO's BankTransaction entity and the bank feeds API both require extra
        scope/permissions. Instead we query the standard accounting entities
        (Purchase = withdrawals, Deposit = deposits) which work with the
        standard accounting scope.
        """
        # Build a lookup: QBO account id -> (erp bank account name, company)
        rows = frappe.db.get_all(
            "Bank Account",
            filters={"integration_id": ["!=", ""]},
            fields=["name", "integration_id", "company"],
        )
        if not rows:
            frappe.throw(_(
                "No bank accounts with an Integration ID found. "
                "Run Fetch Bank Accounts first."
            ))
        acct_map = {r["integration_id"]: r for r in rows}

        since = str(self.bank_txn_since) if self.bank_txn_since else "2020-01-01"
        created = skipped = 0

        for entity, date_field, acct_field, direction in [
            ("Purchase", "TxnDate", "AccountRef",          "withdrawal"),
            ("Deposit",  "TxnDate", "DepositToAccountRef", "deposit"),
        ]:
            c, s = self._fetch_entity_txns(entity, date_field, acct_field, direction, since, acct_map)
            created += c
            skipped += s

        self.db_set("bank_txn_last_synced", now_datetime())

        from metactical.metactical.doctype.qbo_sync_log.qbo_sync_log import log_sync
        log_sync(
            operation="Bank Transactions",
            status="Success",
            records_processed=created + skipped,
            records_created=created,
            notes=f"{skipped} skipped (already imported or account not mapped)",
        )
        return {"created": created, "skipped": skipped}

    def _fetch_entity_txns(self, entity, date_field, acct_field, direction, since, acct_map):
        """Page through one QBO entity type and create Bank Transactions."""
        created = skipped = 0
        start = 1
        page_size = 100

        while True:
            stmt = (
                f"SELECT * FROM {entity} WHERE {date_field} >= '{since}'"
                f" STARTPOSITION {start} MAXRESULTS {page_size}"
            )
            body = self.qbo_query(stmt)
            batch = body.get(entity) or []
            if not batch:
                break

            for txn in batch:
                acct_ref = txn.get(acct_field) or {}
                qbo_acct_id = str(acct_ref.get("value") or "")
                ba = acct_map.get(qbo_acct_id)
                if not ba:
                    skipped += 1
                    continue

                txn_id = f"{entity}-{txn['Id']}"
                if frappe.db.exists("Bank Transaction", {"transaction_id": txn_id}):
                    skipped += 1
                    continue

                amount = abs(float(txn.get("TotalAmt") or 0))
                currency = frappe.db.get_single_value("Global Defaults", "default_currency")
                memo = txn.get("PrivateNote") or txn.get("Memo") or ""
                vendor = ((txn.get("EntityRef") or {}).get("name") or "")
                description = vendor or memo

                doc = frappe.get_doc({
                    "doctype": "Bank Transaction",
                    "bank_account": ba["name"],
                    "date": txn.get("TxnDate"),
                    "deposit":    amount if direction == "deposit"    else 0.0,
                    "withdrawal": amount if direction == "withdrawal" else 0.0,
                    "description": description,
                    "transaction_id": txn_id,
                    "transaction_type": entity,
                    "company": ba["company"],
                    "currency": currency,
                    "status": "Unreconciled",
                })
                doc.insert(ignore_permissions=True)
                doc.submit()
                created += 1

            if len(batch) < page_size:
                break
            start += page_size

        return created, skipped


def _get_or_create_bank(bank_name):
    if frappe.db.exists("Bank", bank_name):
        return bank_name
    return frappe.get_doc({"doctype": "Bank", "bank_name": bank_name}).insert(ignore_permissions=True).name


def get_settings():
    return frappe.get_single("QBO Settings")


# ------------------------------------------------------------------
# Whitelisted entry points (called from form buttons and callback page)
# ------------------------------------------------------------------

@frappe.whitelist()
def get_auth_url():
    doc = frappe.get_single("QBO Settings")
    return doc.get_authorization_url()


@frappe.whitelist(allow_guest=True)
def oauth_callback(code=None, realmId=None, state=None, error=None):
    """Intuit redirects here after the user authorizes (or denies)."""
    if error:
        frappe.log_error(f"QBO OAuth denied: {error}", "QBO OAuth Callback")
        return {"status": "error", "message": error}

    if not code or not state:
        return {"status": "error", "message": "Missing code or state parameter."}

    doc = frappe.get_single("QBO Settings")
    try:
        doc.exchange_code_for_tokens(code=code, realm_id=realmId, state=state)
        return {"status": "success"}
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "QBO OAuth Exchange Failed")
        return {"status": "error", "message": str(e)}


@frappe.whitelist()
def disconnect():
    doc = frappe.get_single("QBO Settings")
    doc.clear_tokens()
    return _("Disconnected from QuickBooks.")


@frappe.whitelist()
def fetch_bank_accounts():
    doc = frappe.get_single("QBO Settings")
    result = doc.fetch_bank_accounts()
    return _("Done: {created} bank account(s) created, {updated} updated.").format(**result)


@frappe.whitelist()
def fetch_bank_transactions():
    doc = frappe.get_single("QBO Settings")
    result = doc.fetch_bank_transactions()
    return _("Done: {created} transaction(s) created, {skipped} skipped.").format(**result)
