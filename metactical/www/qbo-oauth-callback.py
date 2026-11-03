# Copyright (c) 2026, Storebuilder Commerce Inc and contributors
# For license information, please see license.txt
"""Handles the OAuth2 redirect from Intuit after a user authorizes QuickBooks.

Intuit GETs this URL with ?code=...&realmId=...&state=...
We exchange the code for tokens here so the user sees a clean result page.
"""

no_cache = 1

import frappe
from frappe import _


def get_context(context):
    params = frappe.form_dict
    error = params.get("error")
    code = params.get("code")
    realm_id = params.get("realmId")
    state = params.get("state")

    if error:
        context.status = "error"
        context.message = _("QuickBooks authorization was denied: {0}").format(error)
        return

    if not code or not state:
        context.status = "error"
        context.message = _("Missing authorization code. Please try connecting again.")
        return

    try:
        doc = frappe.get_single("QBO Settings")
        doc.exchange_code_for_tokens(code=code, realm_id=realm_id, state=state)
        context.status = "success"
        context.message = _("QuickBooks connected successfully. You can close this window.")
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "QBO OAuth Callback Error")
        context.status = "error"
        context.message = _("Authorization failed: {0}").format(str(e))
