import frappe
import requests


def get_zoho_settings():
    """Return the single Zoho Settings document."""
    return frappe.get_single("Zoho Settings")


@frappe.whitelist()
def zoho_login():
    """Return the Zoho OAuth authorization URL."""
    settings = get_zoho_settings()

    auth_url = (
        f"{settings.auth_url}"
        f"?scope={settings.scope}"
        f"&client_id={settings.client_id}"
        f"&response_type=code"
        f"&access_type=offline"
        f"&prompt=consent"
        f"&redirect_uri={settings.redirect_uri}"
    )
    return {"auth_url": auth_url}


@frappe.whitelist(allow_guest=True)
def zoho_callback(code=None):
    """Receive Zoho OAuth code and exchange it for access/refresh tokens."""
    if not code:
        return {"error": "Missing authorization code"}

    settings = get_zoho_settings()

    data = {
        "grant_type": "authorization_code",
        "client_id": settings.client_id,
        "client_secret": settings.get_password("client_secret"),
        "redirect_uri": settings.redirect_uri,
        "code": code,
    }

    try:
        resp = requests.post(settings.token_url, data=data, timeout=30)
        resp.raise_for_status()
        token_data = resp.json()

        # Update settings with new tokens
        settings.access_token = token_data.get("access_token")
        if token_data.get("refresh_token"):
            settings.refresh_token = token_data.get("refresh_token")
        settings.expires_in = token_data.get("expires_in")
        settings.save(ignore_permissions=True)
        frappe.db.commit()

        return {
            "status": "success",
            "message": "Zoho tokens retrieved successfully",
            "data": token_data,
        }

    except requests.exceptions.RequestException as e:
        frappe.log_error(str(e), "Zoho OAuth Error")
        return {"error": str(e)}


def refresh_zoho_access_token():
    """Refresh Zoho access token using the stored refresh token."""
    settings = get_zoho_settings()
    refresh_token = settings.refresh_token
    if not refresh_token:
        frappe.throw("No refresh token found in Zoho Settings. Please reauthorize with Zoho.")

    data = {
        "grant_type": "refresh_token",
        "client_id": settings.client_id,
        "client_secret": settings.get_password("client_secret"),
        "refresh_token": refresh_token,
    }

    resp = requests.post(settings.token_url, data=data, timeout=30)
    if not resp.ok:
        frappe.log_error(resp.text, "Zoho Token Refresh Failed")
        frappe.throw(f"Failed to refresh Zoho token: {resp.text}")

    token_data = resp.json()
    new_access_token = token_data.get("access_token")
    if not new_access_token:
        frappe.throw("Zoho did not return a new access token.")

    # Update and save
    settings.access_token = new_access_token
    settings.expires_in = token_data.get("expires_in")
    settings.save(ignore_permissions=True)
    frappe.db.commit()

    frappe.logger().info("✅ Zoho access token refreshed successfully.")
    return new_access_token


@frappe.whitelist()
def get_bank_transaction_from_zoho():
    """Fetch bank transactions from Zoho Books and auto-refresh token if expired."""
    settings = get_zoho_settings()
    access_token = settings.access_token
    if not access_token:
        frappe.throw("Access token not found. Please connect to Zoho first.")

    url = f"{settings.domain}/books/v3/banktransactions"
    params = {"organization_id": settings.organization_id, "per_page": 100}
    headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}

    # First attempt
    resp = requests.get(url, headers=headers, params=params, timeout=30)

    # If expired or unauthorized — refresh token and retry once
    if resp.status_code == 401:
        frappe.logger().warning("Zoho access token expired. Refreshing...")
        new_token = refresh_zoho_access_token()
        headers["Authorization"] = f"Zoho-oauthtoken {new_token}"
        resp = requests.get(url, headers=headers, params=params, timeout=30)

    # Final validation
    try:
        resp.raise_for_status()
    except Exception:
        frappe.log_error(resp.text, "Zoho Bank Transaction Fetch Failed")
        frappe.throw(f"Zoho API request failed: {resp.text}")

    return resp.json()
