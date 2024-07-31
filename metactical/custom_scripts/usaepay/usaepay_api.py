import requests
import json
from frappe.utils import cstr
import frappe
import hashlib
import base64
import time
from frappe import _

def get_transaction_from_usaepay(usaepay_transaction_key, headers):	
	usaepay_url = frappe.db.get_single_value("Metactical Settings", "usaepay_url")

	if not usaepay_url:
		frappe.throw(_("USAePay URL not set in Metactical Settings"))

	url = usaepay_url + "/transactions/" + usaepay_transaction_key
	response = requests.get(url, headers=headers)

	if response.status_code == 200:
		transaction = json.loads(response.text)
		if transaction.get("error"):
			frappe.throw(_("Failed to fetch transaction details from USAePay: {0}").format(cstr(transaction.get("error"))))

		return transaction
	else:
		response = json.loads(response.text)
		frappe.throw(_("Failed to fetch transaction details from USAePay: {0}").format(response.get("error")))
	
	return None

def get_token_hash(metactical_settings):
	api_key = metactical_settings.get("api_key")
	pin = metactical_settings.get("pin")
	seed = str(int(time.time()))

	if not api_key or not pin:
		frappe.throw(_("API Key and PIN are required in Metactical Settings"))

	prehash = api_key + seed + pin

	# Generate SHA256 hash
	apihash = 's2/' + seed + '/' + hashlib.sha256(prehash.encode('utf-8')).hexdigest()

	# Generate authKey
	authKey = base64.b64encode((api_key + ":" + apihash).encode('utf-8')).decode('utf-8')

	return "Basic " + authKey

def create_refund(transaction, amount, usaepay_url, headers):
	payload = {
		"amount": amount,
		"trankey": transaction.get("key"),
	}

	if (transaction.get("trantype") == "Credit Card Sale"):
		payload["command"] = "cc:credit"
		payload["creditcard"] = transaction.get("creditcard")
	elif (transaction.get("trantype") == "Check Sale"):
		payload["command"] = "check:credit"
		payload["check"] = transaction.get("check")
	elif (transaction.get("trantype") == "Cash Sale"):
		payload["command"] = "cash:refund"

	if "command" not in payload:
		frappe.throw(_("Transaction type not supported for refund"))

	url = usaepay_url + "/transactions"
	response = requests.post(url, headers=headers, data=json.dumps(payload))

	if response.status_code == 200:
		refund = json.loads(response.text)
		if refund.get("error"):
			frappe.throw(_("Failed to create refund in USAePay: {0}").format(cstr(refund.get("error"))))

		return payload, refund
	else:
		response = json.loads(response.text)
		frappe.throw(_("Failed to create refund in USAePay: {0}").format(response.get("error")))

def get_card_token(usaepay_url, transaction_key, headers):
	payload = {
		"trankey": transaction_key
	}

	response = requests.post(usaepay_url + "/tokens", headers=headers, data=json.dumps(payload))
	if response.status_code == 200:
		token = json.loads(response.text)
		if token.get("error"):
			frappe.throw(_("Failed to get card token from USAePay: {0}").format(cstr(token.get("error"))))
		return token.get("token").get("cardref")
	else:
		response = json.loads(response.text)
		frappe.throw(_(f"Failed to get card token from USAePay: {response.error}"))

def adjust_amount(amount, transaction, usaepay_url, headers=None):
	payload = {
		"command": "cc:adjust",
		"trankey": transaction.get("key"),
		"amount": amount
	}

	response = requests.post(usaepay_url + "/transactions", headers=headers, data=json.dumps(payload))
	if response.status_code == 200:
		adjustment = json.loads(response.text)
		if adjustment.get("error"):
			frappe.throw(_("Failed to make adjustment in USAePay: {0}").format(cstr(adjustment.get("error"))))

		return payload, adjustment
	else:
		response = json.loads(response.text)
		frappe.throw(_("Failed to make adjustment in USAePay: {0}").format(response.get("error")))

def get_customer_detail(customer_key, headers):
	usaepay_url = frappe.db.get_single_value("Metactical Settings", "usaepay_url")
	if not usaepay_url:
		frappe.throw(_("USAePay URL not set in Metactical Settings"))

	url += "/customers/" + customer_key
	response = requests.get(url, headers=headers)

	if response.status_code == 200:
		customer = json.loads(response.text)
		if customer.get("error"):
			frappe.throw(_("Failed to fetch customer details from USAePay: {0}").format(cstr(customer.get("error"))))

		return customer
	else:
		response = json.loads(response.text)
		frappe.throw(_("Failed to fetch customer details from USAePay: {0}").format(response.get("error")))


@frappe.whitelist()
def receive_customer_data():
	response = frappe.form_dict

	event_body = response.get("event_body")
	customer_key = event_body.get("key")

	if "creditcard" in event_body["object"]:
		print("Credit Card found")

	if "check" in event_body["object"]:
		print("Check found")


	