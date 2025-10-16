import frappe
import requests
# ---------- CONFIG ----------
# Zoho
ZOHO_ACCESS_TOKEN = "1000.5ef790705f07d2da571fb4c7393496c5.faa2a25705592bf29c976c112678ba25"
ZOHO_ORG_ID = "902949024"   # your Zoho organization_id
ZOHO_DOMAIN = "https://www.zohoapis.com"   # change if using eu/apac domains

# Which Zoho bank account to fetch (optional)
ZOHO_ACCOUNT_ID = None

# --- CONFIG ---
ZOHO_CLIENT_ID = "1000.AWKI8LYMXHXBEPS7OQQTGIU8ZPTN1Y"
ZOHO_CLIENT_SECRET = "17365ac902fd1d273e4f69a76dc8a8bd06edb823cb"
ZOHO_REDIRECT_URI = "http://metactical_bench2:8014/api/method/metactical.custom_scripts.utils.zoho.zoho_callback"
ZOHO_AUTH_URL = "https://accounts.zoho.com/oauth/v2/auth"
ZOHO_TOKEN_URL = "https://accounts.zoho.com/oauth/v2/token"
ZOHO_SCOPE = "ZohoBooks.fullaccess.all"

# --- STEP 1: Generate login URL ---
@frappe.whitelist()
def zoho_login():
    """
    Redirect the user to Zoho OAuth authorization screen.
    """
    auth_url = (
        f"https://accounts.zoho.com/oauth/v2/auth"
        f"?scope=ZohoBooks.fullaccess.all"
        f"&client_id={ZOHO_CLIENT_ID}"
        f"&response_type=code"
        f"&access_type=offline"
        f"&prompt=consent"
        f"&redirect_uri={ZOHO_REDIRECT_URI}"
    )
    
    return {"auth_url": auth_url}


# --- STEP 2: Handle callback from Zoho ---
@frappe.whitelist(allow_guest=True)
def zoho_callback(code=None):
    """
    Receives the 'code' from Zoho and exchanges it for access and refresh tokens.
    """
    if not code:
        return {"error": "Missing authorization code"}

    data = {
        "grant_type": "authorization_code",
        "client_id": ZOHO_CLIENT_ID,
        "client_secret": ZOHO_CLIENT_SECRET,
        "redirect_uri": ZOHO_REDIRECT_URI,
        "code": code,
    }

    try:
        resp = requests.post(ZOHO_TOKEN_URL, data=data, timeout=30)
        resp.raise_for_status()
        token_data = resp.json()

        exists = frappe.db.exists("Zoho Settings", "Zoho")
        if exists:
            zoho_settings = frappe.get_doc("Zoho Settings", "Zoho")
            zoho_settings.access_token = token_data.get("access_token")
            zoho_settings.refresh_token = token_data.get("refresh_token")
            zoho_settings.expires_in = token_data.get("expires_in")
            zoho_settings.save()
        else:
            zoho_settings = frappe.new_doc("Zoho Settings")
            zoho_settings.api_name = "Zoho"
            zoho_settings.access_token = token_data.get("access_token")
            zoho_settings.refresh_token = token_data.get("refresh_token")
            zoho_settings.expires_in = token_data.get("expires_in")
            zoho_settings.save()
            
        frappe.db.commit()
        return {
            "status": "success",
            "message": "Zoho tokens retrieved successfully",
            "data": token_data
        }

    except requests.exceptions.RequestException as e:
        frappe.log_error(str(e), "Zoho OAuth Error")
        return {"error": str(e)}


def refresh_zoho_access_token():
    """Refresh Zoho access token using stored refresh token."""
    refresh_token = frappe.db.get_single_value("Zoho Settings", "refresh_token")
    if not refresh_token:
        frappe.throw("No refresh token found in Zoho Settings. Please reauthorize with Zoho.")

    data = {
        "grant_type": "refresh_token",
        "client_id": ZOHO_CLIENT_ID,
        "client_secret": ZOHO_CLIENT_SECRET,
        "refresh_token": refresh_token
    }

    resp = requests.post(ZOHO_TOKEN_URL, data=data, timeout=30)
    if not resp.ok:
        frappe.log_error(resp.text, "Zoho Token Refresh Failed")
        frappe.throw(f"Failed to refresh Zoho token: {resp.text}")

    token_data = resp.json()
    new_access_token = token_data.get("access_token")
    if not new_access_token:
        frappe.throw("Zoho did not return a new access token.")

    # Save the new access token
    frappe.db.set_value("Zoho Settings", None, "access_token", new_access_token)
    frappe.db.commit()

    frappe.logger().info("Zoho access token refreshed successfully.")
    return new_access_token


@frappe.whitelist()
def get_bank_transaction_from_zoho():
    """Fetch bank transactions from Zoho Books and auto-refresh token if expired."""
    # Load the current access token from the database
    access_token = frappe.get_doc("Zoho Settings", "Zoho").access_token
    if not access_token:
        frappe.throw("Access token not found. Please connect to Zoho first.")

    url = f"{ZOHO_DOMAIN}/books/v3/banktransactions"
    headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}
    params = {"organization_id": ZOHO_ORG_ID, "per_page": 100}
    if ZOHO_ACCOUNT_ID:
        params["account_id"] = ZOHO_ACCOUNT_ID

    # Try the API call
    resp = requests.get(url, headers=headers, params=params, timeout=30)

    # If unauthorized, refresh and retry once
    if resp.status_code == 401:
        frappe.logger().warning("Zoho access token expired. Refreshing...")
        new_token = refresh_zoho_access_token()

        # Retry with new token
        headers["Authorization"] = f"Zoho-oauthtoken {new_token}"
        resp = requests.get(url, headers=headers, params=params, timeout=30)

    # Final check
    try:
        resp.raise_for_status()
    except Exception:
        frappe.log_error(resp.text, "Zoho Bank Transaction Fetch Failed")
        frappe.throw(f"Zoho API request failed: {resp.text}")

    return resp.json()  # contains 'banktransactions' key
