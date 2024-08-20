import frappe, hashlib, base64, time, requests, json
from frappe.utils import cstr
from frappe import _
from metactical.custom_scripts.utils.metactical_utils import (
	get_customer_address, 
	create_usaepay_log,
	format_json_for_html
)

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

def adjust_amount(amount, transaction, usaepay_url, log, headers=None):
	payload = {
		"command": "cc:adjust",
		"trankey": transaction.get("key"),
		"amount": amount
	}

	frappe.db.set_value("USAePay Log", log.name, "request", format_json_for_html(payload), update_modified=False)
	frappe.db.set_value("USAePay Log", log.name, "amount", amount, update_modified=False)

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
	transaction_key = event_body["object"]["key"]

	docs_to_check = ["Sales Order", "Sales Invoice", "Payment Entry"]
	doctype = ""

	if "invoice" in event_body["object"]:
		if event_body["object"]["invoice"]:
			for doc in docs_to_check:
				if frappe.db.exists(doc, event_body["object"]["invoice"]):
					doctype = doc
					break
		else:
			return
	else:
		metactical_settings = frappe.get_single("Metactical Settings")
		usaepay_url = metactical_settings.get("usaepay_url")
		token_hash = get_token_hash(metactical_settings)

		headers = {
			"Content-Type": "application/json",
			"Authorization": token_hash
		}

		transaction = event_body["object"]["key"]
		transaction = get_transaction_from_usaepay(transaction, headers)
		if not transaction:
			return

		event_body["object"] = transaction

	if not doctype:
		return

	if doctype == "Sales Order":
		process_sales_order(event_body, transaction_key)
	elif doctype == "Payment Entry":
		process_payment_entry(event_body, transaction_key)
	elif doctype == "Sales Invoice":
		process_sales_invoice(event_body, transaction_key)
	else:
		process_credit_card_tokens(event_body, event_body["object"]["customer"])

def process_sales_order(event_body, transaction_key):
	sales_order = frappe.db.get_value("Sales Order", {"po_no": event_body["object"]["invoice"]}, ["name", "customer", "neb_usaepay_transaction_key"], as_dict=1)

	if not sales_order.neb_usaepay_transaction_key:
		frappe.db.set_value("Sales Order", sales_order.name, "neb_usaepay_transaction_key", transaction_key)

	customer = sales_order.customer

	process_credit_card_tokens(event_body, customer)


def process_payment_entry(event_body, transaction_key):
	frappe.db.set_value("Payment Entry", event_body["object"]["invoice"], "reference_no", transaction_key)
	customer = frappe.db.get_value("Payment Entry", event_body["object"]["invoice"], "party")

	process_credit_card_tokens(event_body, customer)

def process_sales_invoice(event_body, transaction_key):
	sales_invoice = frappe.get_doc("Sales Invoice", event_body["object"]["invoice"])
	sales_invoice_items = sales_invoice.items

	# get sales order from sales invoice items
	for item in sales_invoice_items:
		if item.sales_order:
			neb_usaepay_transaction_key = frappe.db.get_value("Sales Order", item.sales_order, "neb_usaepay_transaction_key")
			if not neb_usaepay_transaction_key:
				frappe.db.set_value("Sales Order", item.sales_order, "neb_usaepay_transaction_key", transaction_key)
			break

	process_credit_card_tokens(event_body, sales_invoice.customer)


def process_credit_card_tokens(event_body, customer):
	transaction_key = event_body["object"]["key"]

	if "creditcard" in event_body["object"]:
		tokens = []
		customer_cc = frappe.db.exists("Customer CC", {"erpnext_customer_id": customer})
		if customer_cc:
			existing_cc_tokens = frappe.get_doc("Customer CC", customer_cc)
			tokens = existing_cc_tokens.cc_tokens    
		else:
			customer_cc = frappe.get_doc({
				"doctype": "Customer CC",
				"erpnext_customer_id": customer
			}).insert()

			customer_cc = customer_cc.name

		credit_card_used_in_transaction = event_body["object"]["creditcard"]
		is_cc_new = True

		if tokens:
			for token in tokens:
				if token.cc_number == credit_card_used_in_transaction["number"]:
					is_cc_new = False
					break

		# if the credit card is new, add it to the customer's credit card tokens
		if is_cc_new:
			add_credit_card_token(customer_cc, tokens, credit_card_used_in_transaction, transaction_key)
		frappe.db.commit()

def add_credit_card_token(customer_cc, tokens, credit_card_used_in_transaction, transaction_key):
	headers, usaepay_url = get_headers()
	token = get_card_token(usaepay_url, transaction_key, headers)
	labels = ["Primary", "Secondary", "Third", "Fourth", "Fifth", "Sixth", "Seventh"]

	frappe.get_doc({
		"doctype": "Customer CC Tokens",
		"parent": customer_cc,
		"parentfield": "cc_tokens",
		"parenttype": "Customer CC",
		"label": labels[len(tokens)],
		"token": token,
		"cc_number": credit_card_used_in_transaction["number"],
	}).insert()

def get_headers():
	metactical_settings = frappe.get_single("Metactical Settings")
	usaepay_url = metactical_settings.get("usaepay_url")
	if not usaepay_url:
		frappe.throw(_("USAePay URL not set in Metactical Settings"))

	# Generate token hash
	token_hash = get_token_hash(metactical_settings)
	headers = {
		"Content-Type": "application/json",
		"Authorization": token_hash
	}
	return headers, usaepay_url

def get_token_hash(metactical_settings, pin=None):
	api_key = metactical_settings.get("api_key")

	if not pin:
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

@frappe.whitelist()
def make_payment(customer, amount, token, payment_entry=None):
	if not customer:
		frappe.throw(_("Customer is required"))

	if token:
		token = frappe.db.get_value("Customer CC Tokens", token, "token")

	# get billing address
	addresses = get_customer_address(customer)
	customer_names = None
	if "billing" in addresses:
		customer_names = frappe.db.get_value("Customer", customer, ["first_name", "last_name"], as_dict=1)
		addresses["billing"] = get_mapped_address(addresses["billing"], customer_names)

	headers, usaepay_url = get_headers()

	references = frappe.get_doc("Payment Entry", payment_entry).references
	reference = None
	reference_doctype = None

	if len(references) == 1:
		if references[0].reference_doctype in ["Sales Order", "Sales Invoice"]:
			reference = references[0].reference_name
			reference_doctype = references[0].reference_doctype

	if not reference:
		reference = payment_entry

	log = create_usaepay_log("Payment Entry", payment_entry, "New Payment")
	log = frappe.get_doc("USAePay Log", log.name)

	payload = {
		"amount": amount,
		"command": "cc:sale",
		"invoice": reference,
		"creditcard": {
			"number": token
		},
		"billing": addresses["billing"]
	}

	log.request = format_json_for_html(payload)
	log.action = "New Payment"
	log.reference_docname = reference
	log.reference_doctype = reference_doctype if reference_doctype else "Payment Entry"
	log.payment_entry = payment_entry
	log.amount = amount

	try:
		response = requests.post(usaepay_url + "/transactions", headers=headers, data=json.dumps(payload))
		handle_payment_response(response, log)
		frappe.db.set_value("Payment Entry", payment_entry, "reference_no", log.transaction_key)
	except Exception as e:
		handle_payment_exception(e, log)

def handle_payment_response(response, log):
	if response.status_code == 200:
		transaction = json.loads(response.text)
		log.response = format_json_for_html(transaction)

		if transaction.get("error"):
			log.save()
			frappe.response["success"] = False
			frappe.response["error"] = transaction.get("error")
			return

		log.transaction_key = transaction.get("key")
		frappe.response["success"] = True
	else:
		response = json.loads(response.text)
		log.response = format_json_for_html(response)

		frappe.response["success"] = False
		frappe.response["error"] = response.get("error")
	log.save()

def handle_payment_exception(exception, log):
	log.response = str(exception)
	log.log = frappe.get_traceback()
	log.save()

	frappe.response["success"] = False
	frappe.response["error"] = str(exception)

def get_mapped_address(address, customer_name):
	if not address:
		return {}

	return {
		"firstname": customer_name.get("first_name"),
		"lastname": customer_name.get("last_name"),
		"street": address.get("address_line1"),
		"street2": address.get("address_line2"),
		"city": address.get("city"),
		"state": address.get("state"),
		"postalcode": address.get("pincode"),
		"country": address.get("country"),
		"phone": address.get("phone"),
	}

def get_headers():
	metactical_settings = frappe.get_single("Metactical Settings")
	usaepay_url = metactical_settings.get("usaepay_url")
	if not usaepay_url:
		frappe.throw(_("USAePay URL not set in Metactical Settings"))

	# Generate token hash
	token_hash = get_token_hash(metactical_settings)

	headers = {
		"Content-Type": "application/json",
		"Authorization": token_hash
	}

	return headers, usaepay_url

@frappe.whitelist()
def get_usaepay_transaction_detail(transaction, docname):
	try:
		metactical_settings = frappe.get_single("Metactical Settings")
		usaepay_url = metactical_settings.get("usaepay_url")
		token_hash = get_token_hash(metactical_settings)

		headers = {
			"Content-Type": "application/json",
			"Authorization": token_hash
		}

		transaction = get_transaction_from_usaepay(transaction, headers)

		# # refunds
		# refunds = frappe.get_all("USAePay Log", filters={"reference_docname": docname, "action": "Refund"}, fields=["refund_amount", "transaction_key"])
		# if refunds:
		# 	transaction["refunds"] = refunds
			
		# 	total_refund = sum([flt(refund.get("refund_amount")) for refund in refunds])
		# 	if total_refund:
		# 		transaction["available_amount"] = float(transaction.get("amount")) - total_refund
		# else:
		# 	transaction["refunds"] = []
		# 	transaction["available_amount"] = transaction.get("amount")

		if transaction:
			frappe.response["transaction"] = transaction
		else:
			frappe.throw("Transaction not found in USAePay")

		return transaction
		 
	except Exception as e:
		frappe.log_error(title="USAePay Transaction Detail Error", message=frappe.get_traceback())
		frappe.msgprint("Unable to get USAePay transaction detail: {0}".format(e), title="Error")


@frappe.whitelist()
def refund_payment(docname, refund_reason, refund_amount):
	user_roles = get_usaepay_roles()
	if not any(role in frappe.get_roles() for role in user_roles.get("refund")):
		frappe.msgprint("You are not authorized to refund payment", title="Error")
		return

	# log = create_usaepay_log(payload, refund_response, "Sales Order", docname, refund_amount, "Refund", refund_reason)
	log = create_usaepay_log("Sales Order", docname, "Refund")

	try:
		sales_order = frappe.get_doc("Sales Order", docname)
		usaepay_transaction_key = sales_order.get("neb_usaepay_transaction_key")
		
		metactical_settings = frappe.get_single("Metactical Settings")
		usaepay_url = metactical_settings.get("usaepay_url")

		# Generate token hash
		token_hash = get_token_hash(metactical_settings)

		headers = {
			"Content-Type": "application/json",
			"Authorization": token_hash
		}

		# get transaction details from USAePay
		transaction = get_transaction_from_usaepay(usaepay_transaction_key, headers)
		if transaction:
			# Generate card token
			card_token = get_card_token(usaepay_url, transaction.get("key"), headers)
			transaction["creditcard"]["number"] = card_token

			# process refund
			payload, refund_response = create_refund(transaction, refund_amount, usaepay_url, headers)

			log.request = format_json_for_html(payload)
			log.response = format_json_for_html(refund_response)
			log.amount = refund_amount
			log.transaction_key = payload.get("trankey")
			log.refund_transaction_key = refund_response.get("key")
			log.refund_reason = refund_reason
			log.save()

			# create USAePay log
			refunded_amount = refund_amount if refund_amount else transaction["amount"]

			card_holder = "for <b>" + refund_response.get("creditcard").get("cardholder") +"</b>" if refund_response.get("creditcard") else ""
			frappe.msgprint(f"<b>{refund_response['auth_amount']}</b> is refunded successfully {card_holder}.")

			return refund_response, log.name
		else:
			frappe.response["success"] = False
			frappe.response["message"] = "Transaction not found in USAePay"
			return None, None

	except Exception as e:
		frappe.log_error(title="Refund Payment Error", message=frappe.get_traceback())
		frappe.throw("Unable to refund payment: {0}".format(e))

@frappe.whitelist()
def adjust_payment(docname, advance_paid=None):
	user_roles = get_usaepay_roles()
	if not any(role in frappe.get_roles() for role in user_roles.get("adjust")):
		frappe.msgprint("You are not authorized to refund payment", title="Error")
		return
	
	# create USAePay log
	log = create_usaepay_log("Sales Order", docname, "Adjustment")

	try:
		sales_order = frappe.get_doc("Sales Order", docname)
		usaepay_transaction_key = sales_order.get("neb_usaepay_transaction_key")
		metactical_settings = frappe.get_single("Metactical Settings")
		usaepay_url = metactical_settings.get("usaepay_url")

		# Generate token hash
		token_hash = get_token_hash(metactical_settings)

		headers = {
			"Content-Type": "application/json",
			"Authorization": token_hash
		}

		# get transaction details from USAePay
		transaction = get_transaction_from_usaepay(usaepay_transaction_key, headers)
		if transaction:
			# update log
			frappe.db.set_value("USAePay Log", log.name, "transaction_key", transaction.get("key"))

			# process the adjustment
			amount = advance_paid if advance_paid else sales_order.grand_total
			payload, adjust_response = adjust_amount(sales_order.grand_total, transaction, usaepay_url, log, headers)
			
			log = frappe.get_doc("USAePay Log", log.name)
			log.response = format_json_for_html(adjust_response)
			log.transaction_key = payload.get("trankey")
			log.save()

			frappe.response["message"] = f"Payment adjusted successfully. New amount is <b>{adjust_response['auth_amount']}</b>"
			frappe.response["success"] = True

			return adjust_response, log.name
		else:
			log.log = f"Transaction {usaepay_transaction_key} not found in USAePay"
			log.save()

			frappe.response["success"] = False
			frappe.response["message"] = "Transaction not found in USAePay"
	
	except Exception as e:
		frappe.db.set_value("USAePay Log", log.name, "log", frappe.get_traceback(), update_modified=False)

		# frappe.log_error(title="Adjust Payment Error", message=frappe.get_traceback())
		frappe.msgprint("Unable to adjust payment: {0}".format(e), title="Error")

@frappe.whitelist()
def get_usaepay_roles():
	try:
		metactical_settings = frappe.get_single("Metactical Settings")
		
		refund = metactical_settings.get("roles_to_refund")
		adjust = metactical_settings.get("roles_to_adjust_payment")
		make_payment = metactical_settings.get("roles_to_make_payment")

		return {
			"refund": [role.role for role in refund],
			"adjust": [role.role for role in adjust],
			"make_payment": [role.role for role in make_payment]
		}
	except Exception as e:
		frappe.log_error(title="USAePay Roles Error", message=frappe.get_traceback())
		frappe.msgprint("Unable to get USAePay roles: {0}".format(e), title="Error")