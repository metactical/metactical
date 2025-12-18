import frappe, hashlib, base64, time, requests, json, time
from frappe.utils import cstr
from frappe import _
from metactical.custom_scripts.utils.metactical_utils import (
	get_customer_address, 
	create_usaepay_log,
	format_json_for_html,
	get_usaepay_account
)

import sys
import time

from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry


def get_transaction_from_usaepay(usaepay_transaction_key, headers, merchant_id=None):	
	if merchant_id:
		usaepay_account = get_usaepay_account(None, merchant_id)
	else:
		usaepay_account = get_usaepay_account(usaepay_transaction_key)

	if not usaepay_account:
		return None 

	usaepay_url = usaepay_account.get("usaepay_url")
	if not usaepay_url:
		frappe.throw(_("USAePay URL not set in USAePay Settings"))

	url = usaepay_url + "/transactions/" + usaepay_transaction_key
	response = safe_get(url, headers)

	if response.status_code == 200:
		transaction = json.loads(response.text)
		if transaction.get("error"):
			# frappe.throw(_("Failed to fetch transaction details from USAePay: {0}").format(cstr(transaction.get("error"))))
			frappe.throw(_("{0} - Failed to fetch transaction details from USAePay - {1}").format(usaepay_transaction_key, cstr(transaction.get("error"))))
		return transaction
	else:
		response = json.loads(response.text)
		frappe.throw(_("{0} - Failed to fetch transaction details from USAePay: {1}").format(usaepay_transaction_key, response.get("error")))
	
	return None

def get_token_hash(usaepay_account):
	api_key = usaepay_account.get("api_key")
	pin = usaepay_account.get("pin")
	seed = str(int(time.time()))

	if not api_key or not pin:
		frappe.throw(_("API Key and PIN are required in USAePay Settings"))

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

	# response = requests.post(usaepay_url + "/tokens", headers=headers, data=json.dumps(payload))
	response = safe_post(usaepay_url + "/tokens", headers, payload)
	if response.status_code == 200:
		token = json.loads(response.text)
		if token.get("error"):
			frappe.throw(_("Failed to get card token from USAePay: {0}").format(cstr(token.get("error"))))
		return token.get("token").get("cardref")
	else:
		response = json.loads(response.text)
		frappe.throw(_(f"Failed to get card token from USAePay: {response}"))
  
def safe_post(url, headers, payload, retries=3, backoff=2):
    for attempt in range(retries):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=15)
            return response
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            if attempt < retries - 1:
                time.sleep(backoff * (2 ** attempt))  # exponential backoff
            else:
                raise e

def safe_get(url, headers, retries=3, backoff=2):
	for attempt in range(retries):
		try:
			response = requests.get(url, headers=headers, timeout=15)
			return response
		except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
			if attempt < retries - 1:
				time.sleep(backoff * (2 ** attempt))

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

# def get_customer_detail(customer_key, headers):
# 	usaepay_url = frappe.db.get_single_value("USAePay Settings", "usaepay_url")
# 	if not usaepay_url:
# 		frappe.throw(_("USAePay URL not set in USAePay Settings"))

# 	url += "/customers/" + customer_key
# 	response = requests.get(url, headers=headers)

# 	if response.status_code == 200:
# 		customer = json.loads(response.text)
# 		if customer.get("error"):
# 			frappe.throw(_("Failed to fetch customer details from USAePay: {0}").format(cstr(customer.get("error"))))

# 		return customer
# 	else:
# 		response = json.loads(response.text)
# 		frappe.throw(_("Failed to fetch customer details from USAePay: {0}").format(response.get("error")))

@frappe.whitelist()
def receive_customer_data(response=None, docname=None):
	try:  
		if not response:
			response = frappe.form_dict

		event_body = response.get("event_body")
		if response.get('event_type') == "transaction.sale.refunded":
			return

		transaction_key = event_body["object"]["key"]

		docs_to_check = ["Sales Order", "Sales Invoice", "Payment Entry"]
		doctype = ""

		# check if the trnsaction is initiated from a payment Entry in the ERP
		if "invoice" in event_body["object"] and event_body["object"]["invoice"]:
			if event_body["object"]["invoice"]:
				for doc in docs_to_check:
					if frappe.db.exists(doc, event_body["object"]["invoice"]):
						doctype = doc
						break
			else:
				return

		# doctype = the doctype referenced in the Payment Entry or the Sales order created by the SB
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
   
		frappe.db.commit()
		
		# log the response from USAePay if the transaction is initiated from the ERP and paid from the ERP
		try:
			log = frappe.db.get_value("USAePay Log", {"reference_docname": event_body["object"]["invoice"], "action": "New Payment", "reference_doctype": doctype}, ["name", "response", "payment_entry"], as_dict=True)
			if log:
				if not log.response:
					frappe.db.set_value("USAePay Log", log.name, "response", format_json_for_html(event_body), update_modified=False)
					frappe.db.set_value("USAePay Log", log.name, "transaction_key", event_body["object"]["key"], update_modified=False)
				
				if log.payment_entry:
					if not frappe.db.get_value("Payment Entry", log.payment_entry, "reference_no"):
						frappe.db.set_value("Payment Entry", log.payment_entry, "reference_no", event_body["object"]["key"], update_modified=False)
					

					if frappe.db.get_value("Payment Entry", log.payment_entry, "docstatus") == 0:
						frappe.get_doc("Payment Entry", log.payment_entry).submit()
		except Exception as e:
			frappe.log_error(title="USAePay Log Update Error", message=frappe.get_traceback())	

	except frappe.ValidationError as e:
		frappe.db.commit()
	except Exception as e:
		frappe.log_error(title="USAePay Log Update Error", message=frappe.get_traceback())

def get_usaepay_order_detail(transaction, order, logger):
	usaepay_account = get_usaepay_account(lead_source=order.source)
	if logger:
		logger.error(f"USAePay account: {usaepay_account.lead_source}, authorizeTransactionId: {transaction.get('authorizeTransactionId')}")
	
	if not usaepay_account:
		frappe.throw(_("USAePay account not found for the lead source {0}").format(order.source))
		
	headers, usaepay_url = get_headers(lead_source=order.source)
	if not usaepay_url:
		frappe.log_error(title="USAePay URL not set", message="USAePay URL is not set in USAePay Settings for the lead source {0}".format(order.source))

	if not transaction["authorizeTransactionId"]:
		return 

	transaction = get_transaction_from_usaepay(transaction["authorizeTransactionId"], headers, usaepay_account.get("merchant_id"))
	if logger:
		if transaction:
			logger.error(f"Transaction details fetched from USAePay")
		else:
			logger.error(f"Transaction details not found in USAePay for transaction key: {transaction['authorizeTransactionId']}")

	event_body = {}
	event_body["object"] = frappe._dict(transaction)

	# create payment entry if the transaction is successful
	process_sales_order(event_body, transaction["key"], logger)
	so_usaepay_transaction = frappe.db.get_value("SO USAePay Transaction", {"order_id": order.name}, "name")
	if so_usaepay_transaction:
		frappe.delete_doc("SO USAePay Transaction", so_usaepay_transaction)
		frappe.db.commit()

def process_sales_order(event_body, transaction_key, logger=None):
	sales_order = frappe.db.get_value("Sales Order", {"po_no": event_body["object"]["invoice"]}, ["name", "customer", "neb_usaepay_transaction_key", "po_no", "company", "source"], as_dict=1)
	if not sales_order:
		sales_order = frappe.db.get_value("Sales Order", event_body["object"]["invoice"], ["name", "customer", "neb_usaepay_transaction_key", "po_no", "company", "source"], as_dict=1)
	
		if not sales_order:
			if logger:
				logger.error(f"Sales Order not found for PO No: {event_body['object']['invoice']}")
			return

	if not sales_order["neb_usaepay_transaction_key"]:
		frappe.db.set_value("Sales Order", sales_order.name, "neb_usaepay_transaction_key", transaction_key)
		frappe.db.commit()

	customer = sales_order.customer
	sales_order.doctype = "Sales Order"
	process_credit_card_tokens(event_body, customer, sales_order.source, logger)
	
	# create USAePay log
	log = create_log(sales_order, event_body)
	payment_entry = create_payment_entry(sales_order, event_body, log, logger)
	if logger and payment_entry:
		logger.error("Process Completed for Sales Order: {0} and Payment Entry: {1}".format(sales_order.name, payment_entry.name))
	else: 
		logger.error("Unable to create Payment Entry for Sales Order: {0}".format(sales_order.name))

def process_payment_entry(event_body, transaction_key):
	frappe.db.set_value("Payment Entry", event_body["object"]["invoice"], "reference_no", transaction_key)
	if frappe.db.get_value("Payment Entry", event_body["object"]["invoice"], "docstatus") == 0:
		frappe.get_doc("Payment Entry", event_body["object"]["invoice"]).submit()
  
	customer = frappe.db.get_value("Payment Entry", event_body["object"]["invoice"], "party")
	
	# update the sales order with the transaction key
	references = frappe.get_doc("Payment Entry", event_body["object"]["invoice"]).references
	if references:
		if len(references) == 1:
			if references[0].reference_doctype == "Sales Order":
				frappe.db.set_value("Sales Order", references[0].reference_name, "neb_usaepay_transaction_key", transaction_key)

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

	customer = sales_invoice.customer
	sales_invoice.doctype = "Sales Invoice"
	
	# process credit card tokens
	process_credit_card_tokens(event_body, sales_invoice.customer, sales_invoice.source)

	log = create_log(sales_invoice, event_body)
	create_payment_entry(sales_invoice, event_body, log)

def get_payment_entries(doc):
	payment_entries = frappe.db.sql("""
		SELECT paid_amount, pe.name, pe.reference_no
		FROM `tabPayment Entry Reference` per
		JOIN `tabPayment Entry` pe ON pe.name = per.parent
		where per.reference_doctype = %s and per.reference_name = %s and pe.docstatus = 1
	""", (doc.doctype, doc.name), as_dict=1)

	return payment_entries

# create USAePay log for payments that will be done from the payment form 
def create_log(doc, event_body):
	log = ""
	payment_entries = get_payment_entries(doc)
	log_type = ""

	# log the response from USAePay if the transaction is initiated from the Payment Request
	if len(payment_entries) == 0:
		log_type = "New Payment"
	else:
		log_type = "Adjustment"
		
	if log_type:
		log = create_usaepay_log(doc.doctype, doc.name, log_type)
		amount = event_body["object"]["auth_amount"] if "auth_amount" in event_body["object"] else event_body["object"]["amount"]

		frappe.db.set_value("USAePay Log", log.name, "response", format_json_for_html(event_body), update_modified=False)
		frappe.db.set_value("USAePay Log", log.name, "transaction_key", event_body["object"]["key"], update_modified=False)
		frappe.db.set_value("USAePay Log", log.name, "amount", amount, update_modified=False)
		payment_requests = frappe.get_all("Payment Request", 
												filters={
													"reference_doctype": doc.doctype, 
													"reference_name": doc.name, 
													"docstatus": 1, 
													"status": "Requested",
													"grand_total": amount
												}, fields=["name"])

		if payment_requests:
			frappe.db.set_value("USAePay Log", log.name, "request", "<a href='/app/payment-request/{0}'>Payment Request</a>".format(payment_requests[0].name), update_modified=False)

		create_comment(log.name)
	return log

def create_comment(log):
    if not frappe.db.exists("USAePay Log", log):
        log = frappe.get_doc("USAePay Log", log)

        comment = get_comment_message(log)
        doctypes = {}
        
        if log.reference_doctype == "Payment Entry":
            doctypes["Payment Entry"] = log.reference_docname

            references = frappe.get_doc("Payment Entry", log.reference_docname).references
            if references:
                doctypes[references[0].reference_doctype] = references[0].reference_name
        
        if log.sales_return:
            doctypes["Sales Invoice"] = log.sales_return
        
        for dt in doctypes:
            frappe.get_doc({
				'doctype': 'Comment',
				'content': comment,
				'reference_doctype': dt,
				"comment_type": "Comment",
				'reference_name': doctypes[dt],
			}).save(ignore_permissions=True)
			
        frappe.db.commit()    
        
    
def get_comment_message(log):
    comment = "*USAePay Log*\n"    
    comment += f"Action: {log.action}\n"
    
    if log.transaction_key:
        comment += f"Transaction Key: {log.transaction_key}\n"
    
    if log.payment_entry:
        comment += f"Payment Entry: {log.payment_entry}\n"
    
    if log.sales_return:
        comment += f"Sales Return: {log.sales_return}\n"
        comment += f"Refund Transaction Key: {log.refund_transaction_key}\n"
        
    if frappe.session.user:
        comment += f"Processed by: {frappe.session.user}\n"
        
    comment += f"Amount: {log.amount}\n"
	
    return comment

def create_payment_entry(doc, data, log, logger=None):
	try: 
		if logger:
			logger.error(f"Creating payment entry for {doc.name}")
		mode_of_payment = "Visa"
		
		if 'category_code' in data["object"]["creditcard"]:
			if data["object"]["creditcard"]["category_code"] == "AX":
				mode_of_payment = "Amex"
			elif data["object"]["creditcard"]["category_code"] == "M":
				mode_of_payment = "Master Card"

		pe = get_payment_entry(doc.doctype, doc.name)
		pe.mode_of_payment = mode_of_payment
		pe.paid_amount = data["object"]["auth_amount"] if "auth_amount" in data["object"] else data["object"]["amount"]
		pe.reference_no = data["object"]["key"]
		pe.reference_date = frappe.utils.now()
		pe.set_missing_values()
		
		if pe.references:
			outstanding_amount = pe.references[0].outstanding_amount
			allocated = pe.references[0].allocated_amount if outstanding_amount >= pe.references[0].allocated_amount else outstanding_amount
			
			amount = data["object"]["auth_amount"] if "auth_amount" in data["object"] else data["object"]["amount"]
			if float(allocated) > float(amount):
				pe.references[0].allocated_amount = float(amount)
		
		if float(pe.paid_amount) > 0:
			pe.save()
			frappe.db.commit()
			if logger:
				logger.error(f"Payment Entry {pe.name} created with amount {pe.paid_amount}")
			try:
				pe.submit()
				logger.error(f"Payment Entry {pe.name} submitted")
			except Exception as e:
				frappe.log_error(title="Payment Entry Submission Error", message=frappe.get_traceback())

		if log:
			frappe.db.set_value("USAePay Log", log.name, "payment_entry", pe.name, update_modified=False)
		
		frappe.db.commit()
		return pe
	except Exception as e:
		logger.error(f"Error creating payment entry for {doc.name}: {e}")
		frappe.log_error(title="PE Creation from USAePay Error", message=frappe.get_traceback())

def process_credit_card_tokens(event_body, customer, lead_source=None, logger=None):
	transaction_key = event_body["object"]["key"]
	
	if logger:
		logger.error(f"Processing credit card tokens for customer: {customer}, transaction key: {transaction_key}")
  
	if "creditcard" in event_body["object"]:
		tokens = []
		customer_cc = frappe.db.exists("Customer CC", {"erpnext_customer_id": customer})
		if customer_cc:
			existing_cc_tokens = frappe.get_doc("Customer CC", customer_cc)
			tokens = existing_cc_tokens.cc_tokens    
			if logger:
				logger.error(f"Customer CC found: {customer_cc}")
		else:
			customer_cc = frappe.get_doc({
				"doctype": "Customer CC",
				"erpnext_customer_id": customer
			}).insert()

			customer_cc = customer_cc.name

			if logger:
				logger.error(f"Customer CC is created")
   
		credit_card_used_in_transaction = event_body["object"]["creditcard"]
		is_cc_new = True
		existing_token_id = None
		if tokens:
			for token in tokens:
				if token.cc_number == credit_card_used_in_transaction["number"]:
					is_cc_new = False
					existing_token_id = token.name
					break

		# if the credit card is new, add it to the customer's credit card tokens
		if is_cc_new:
			add_credit_card_token(customer_cc, tokens, credit_card_used_in_transaction, transaction_key, event_body, lead_source)
		else:
			frappe.db.set_value("Customer CC Tokens", existing_token_id, "card_holder", credit_card_used_in_transaction.get("cardholder"))
   
		frappe.db.commit()
	
		if logger:
			logger.error(f"Credit card tokens processed for customer: {customer}")

def add_credit_card_token(customer_cc, tokens, credit_card_used_in_transaction, transaction_key, event_body, lead_source=None):
	headers, usaepay_url = get_headers(event_body, lead_source)
	token = get_card_token(usaepay_url, transaction_key, headers)
	labels = ["Primary", "Secondary", "Third", "Fourth", "Fifth", "Sixth", "Seventh", "Eighth", "Ninth", "Tenth"]

	try:
		frappe.get_doc({
			"doctype": "Customer CC Tokens",
			"parent": customer_cc,
			"parentfield": "cc_tokens",
			"parenttype": "Customer CC",
			"card_holder": credit_card_used_in_transaction.get("cardholder"),
			"label": labels[len(tokens)],
			"token": token,
			"cc_number": credit_card_used_in_transaction["number"],
		}).insert()
	except Exception as e:
		frappe.log_error(title="Customer Token Insertion Error", message=frappe.get_traceback())

def get_headers(transaction=None, lead_source=None):
	if lead_source:
		usaepay_account = get_usaepay_account(None, None, lead_source)
	elif transaction and "merchant" in transaction:
		merchant_id = transaction["merchant"]["merch_key"]
		usaepay_account = get_usaepay_account(None, merchant_id)
	elif transaction:
		usaepay_account = get_usaepay_account(transaction["object"]["key"])
	else:
		usaepay_account = get_usaepay_account()

	if not usaepay_account:
		return "", ""

	# Generate token hash
	usaepay_url = usaepay_account.get("usaepay_url")
	token_hash = get_token_hash(usaepay_account)
	headers = {
		"Content-Type": "application/json",
		"Authorization": token_hash
	}
	return headers, usaepay_url

def get_token_hash(usaepay_account, pin=None):
	api_key = usaepay_account.get("api_key")

	if not pin:
		pin = usaepay_account.get("pin")
	
	seed = str(int(time.time()))
	if not api_key or not pin:
		frappe.throw(_("API Key and PIN are required in USAePay Settings"))
	
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
		customer_cc = frappe.db.get_value("Customer CC Tokens", token, ["token", "card_holder"], as_dict=1)
		if not customer_cc:
			frappe.throw(_("Invalid card token"))

	# get billing address
	addresses = get_customer_address(customer)
	customer_names = None
	if "billing" in addresses:
		customer_names = frappe.db.get_value("Customer", customer, ["first_name", "last_name"], as_dict=1)
		addresses["billing"] = get_mapped_address(addresses["billing"], customer_names)

	# get lead source and reference doctype
	references = frappe.get_doc("Payment Entry", payment_entry).references
	reference = None
	reference_doctype = None
	lead_source = None

	if len(references) == 1:
		if references[0].reference_doctype in ["Sales Order", "Sales Invoice"]:
			reference = references[0].reference_name
			reference_doctype = references[0].reference_doctype
			lead_source = frappe.db.get_value(references[0].reference_doctype, references[0].reference_name, "source")
	
	headers, usaepay_url = get_headers(lead_source=lead_source)
	if not reference:
		reference = payment_entry

	log = create_usaepay_log("Payment Entry", payment_entry, "New Payment")
	log = frappe.get_doc("USAePay Log", log.name)

	payload = {
		"amount": amount,
		"command": "cc:sale",
		"invoice": reference,
		"creditcard": {
			"cardholder": customer_cc.card_holder if customer_cc and customer_cc.card_holder else (customer_names.get("first_name") + " " + customer_names.get("last_name")) if customer_names else "",
			"number": customer_cc.token,
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
		
		if reference_doctype == "Sales Order":
			frappe.db.set_value("Sales Order", reference, "neb_usaepay_transaction_key", log.transaction_key)

		# submit payment entry
		payment_entry_doc = frappe.get_doc("Payment Entry", payment_entry)
		if payment_entry_doc.docstatus == 0:
			payment_entry_doc.submit()
  
		create_doc_comment(payment_entry_doc, log)
		
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

@frappe.whitelist()
def get_usaepay_transaction_detail(transaction, docname):
	try:
		lead_source = frappe.db.get_value("Sales Order", docname, "source")
		usaepay_account = get_usaepay_account(transaction_key=transaction, lead_source=lead_source)
		usaepay_url = usaepay_account.get("usaepay_url")
		token_hash = get_token_hash(usaepay_account)

		headers = {
			"Content-Type": "application/json",
			"Authorization": token_hash
		}

		transaction = get_transaction_from_usaepay(transaction, headers)

		# refunds
		refunds = frappe.get_all("USAePay Log", filters={"reference_docname": docname, "action": "Refund"}, fields=["refund_amount", "transaction_key"])
		if refunds:
			transaction["refunds"] = refunds
			
			total_refund = sum([flt(refund.get("refund_amount")) for refund in refunds])
			if total_refund:
				transaction["available_amount"] = float(transaction.get("amount")) - total_refund
		else:
			transaction["refunds"] = []
			transaction["available_amount"] = transaction.get("amount")

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
		usaepay_account = get_usaepay_account(transaction_key=sales_order.neb_usaepay_transaction_key ,lead_source=sales_order.source)
		usaepay_url = usaepay_account.get("usaepay_url")

		# Generate token hash
		token_hash = get_token_hash(usaepay_account)

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
			card_holder = transaction["creditcard"].get("cardholder")

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
			if card_holder:
				if "cardholder" in refund_response.get("creditcard"):
					card_holder = refund_response.get("creditcard").get("cardholder")
					frappe.msgprint(f"<b>$ {refunded_amount}</b> is refunded successfully for <b>{card_holder}</b>.")
				# else:
					# frappe.msgprint(f"<b>$ {refunded_amount}</b> is refunded successfully.")
			# else:
				# frappe.msgprint(f"<b>$ {refunded_amount}</b> is refunded successfully.")

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
		usaepay_account = get_usaepay_account(transaction_key=sales_order.neb_usaepay_transaction_key ,lead_source=sales_order.source)
		usaepay_url = usaepay_account.get("usaepay_url")

		# Generate token hash
		token_hash = get_token_hash(usaepay_account)

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
		return None, None

def void_payment_in_usaepay(doc):
	doctype = doc.doctype
	docname = doc.name
	reference_no = doc.reference_no

	# get lead source
	lead_source = None
	for ref in doc.references:
		if ref.reference_doctype in ["Sales Order", "Sales Invoice"]:
			lead_source = frappe.db.get_value(ref.reference_doctype, ref.reference_name, "source")
			break

	usaepay_account = get_usaepay_account(transaction_key=reference_no, lead_source=lead_source)
	usaepay_url = usaepay_account.get("usaepay_url")

	# Generate token hash
	token_hash = get_token_hash(usaepay_account)

	headers = {
		"Content-Type": "application/json",
		"Authorization": token_hash
	}

	args = {
		"trankey": reference_no,
		"command": "void"
	}

	log = create_usaepay_log(doctype, docname, "Void")
	log.request = format_json_for_html(args)

	try:
		response = requests.post(usaepay_url + "/transactions", headers=headers, data=json.dumps(args))
		if response.status_code == 200:
			void_response = json.loads(response.text)
			log.response = format_json_for_html(void_response)
			log.save()

			frappe.response["message"] = f"Payment voided successfully"
			frappe.response["success"] = True
   
			create_doc_comment(doc, log)

			return void_response, log.name
		else:
			response = json.loads(response.text)
			log.response = format_json_for_html(response)
			log.save()

			frappe.throw("Unable to void payment: {0}".format(response.get("error")))
	except Exception as e:
		log.log = frappe.get_traceback()
		log.save()

		frappe.throw("Unable to void payment: {0}".format(e))

@frappe.whitelist()
def get_usaepay_roles():
	try:
		metactical_settings = frappe.get_single("USAePay Settings")
		
		refund = metactical_settings.get("roles_to_refund")
		adjust = metactical_settings.get("roles_to_adjust_payment")
		make_payment = metactical_settings.get("roles_to_make_payment")
		cancel_payment = metactical_settings.get("roles_to_cancel_payment")
		
		return {
			"refund": [role.role for role in refund],
			"adjust": [role.role for role in adjust],
			"make_payment": [role.role for role in make_payment],
			"cancel_payment": [role.role for role in cancel_payment]
		}
	except Exception as e:
		frappe.log_error(title="USAePay Roles Error", message=frappe.get_traceback())
		frappe.msgprint("Unable to get USAePay roles: {0}".format(e), title="Error")

@frappe.whitelist()
def add_to_log(log):
	log = json.loads(log)
	payment_entry = log.get("payment_entry")
	invoice = log.get("invoice")
	amount = log.get("amount")
	billing_address = log.get("billing_address")
	doctype = "Payment Entry"

	if frappe.db.exists("Sales Invoice", invoice):
		doctype = "Sales Invoice"
	elif frappe.db.exists("Sales Order", invoice):
		doctype = "Sales Order"

	request = {
		"amount": amount,
		"command": "cc:sale",
		"invoice": invoice,
		"billing": billing_address
	}

	frappe.get_doc({
		"doctype": "USAePay Log",
		"payment_entry": payment_entry,
		"invoice": invoice,
		"amount": amount,
		"request": format_json_for_html(request),
		"action": "New Payment",
		"reference_doctype": doctype,
		"reference_docname": invoice,
		"date": frappe.utils.now()
	}).insert()

def get_lead_source(transaction_key):
	return frappe.db.get_value("Sales Order", {"neb_usaepay_transaction_key": transaction_key}, "source")

def process_missed_usaepay_transactions():
	# Get all USAePay transactions that are not linked to any Sales Order or Payment Entry
	usaepay_transactions = frappe.get_all("SO USAePay Transaction", fields=["name", "transaction_key", "order_id"])
	for transaction in usaepay_transactions:
		# convert payload to dict
		order = frappe.get_doc("Sales Order", transaction.order_id)
		so_transaction = {"authorizeTransactionId": transaction.transaction_key}

		if order and order.advance_paid == 0:
			try:
				frappe.enqueue(get_usaepay_order_detail, 
							   transaction=so_transaction, 
							   order=order, 
							   logger=None,
							   queue='long', 
							   timeout=600, 
							   event='get_usaepay_order_detail')
			except Exception as e:
				frappe.log_error(title="USAePay Order Detail Fetch Error", message=frappe.get_traceback())
		else:
			if order.advance_paid > 0:
				frappe.delete_doc("SO USAePay Transaction", transaction["name"])
			else:
				frappe.log_error(title="USAePay Order Not Found", message="Sales Order not found for transaction {0}".format(transaction["transaction_key"]))


def create_doc_comment(doc, log):
	try:
		message = f"{frappe.session.user} performed '{log.action}' action in USAePay and the log is <a href='/app/usaepay-log/{log.name}'>here</a>."
		frappe.get_doc({
			"doctype": "Comment",
			"reference_doctype": doc.doctype,
			"reference_name": doc.name,
			"comment_type": "Comment",
			"content": message
		}).insert(ignore_permissions=True)
		frappe.db.commit()
	except Exception as e:
		frappe.log_error(title="Comment Creation Error", message=frappe.get_traceback())