import frappe
from metactical.custom_scripts.utils.metactical_utils import remove_tz_from_date, post_to_rocket_chat
from metactical.custom_scripts.payment_entry.payment_entry import get_payment_entry
from erpnext.accounts.doctype.sales_invoice.sales_invoice import get_bank_cash_account
from erpnext.accounts.doctype.payment_entry.payment_entry import get_account_details
import logging
import json, ast, os, sys, pathlib, subprocess
from metactical.custom_scripts.controllers.accounts_controller import update_child_qty_rate

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = frappe.logger("rmq_log", allow_site=True, file_count=100)

def get_bench_path():
	# Start from current directory and move upward until we find `sites` folder
	current = os.path.abspath(os.getcwd())
	while current != os.path.dirname(current):  # stop at root
		if os.path.isdir(os.path.join(current, "sites")):
			return current
		current = os.path.dirname(current)
	return None
  
def process_rmq_data(parsedContent):
	try:
		frappe.set_user("rmqorders@metactical.com")
		rmq_log = create_rmq_log(parsedContent)
		
		logger.error("\n\n")
		logger.error(f"Received RMQ data: Order Number: {parsedContent['orderNumber']}, Publisher Site: {parsedContent['publisher_site']}")

		# Assign the shipping province and country based on the parsed content.
		# If not provided, default to "Alberta" for the province and "Canada" for the country.
		province = parsedContent['shippingRegion']['name'] if parsedContent.get("shippingRegion") else "Alberta"
		country = parsedContent['shippingCountry']['name'] if parsedContent.get("shippingCountry") else "Canada"
		frappe.form_dict["account"] = ""

		# Retrieve the default company name from the Global Defaults doctype in Frappe.
		
		company = frappe.db.get_value("Lead Source", parsedContent["publisher_site"], "neb_company") or frappe.db.get_single_value("Global Defaults", "default_company")  
  
		# Initialize the shipping item as None. If a shipping description exists,
		# use it to fetch the corresponding shipping item and cost.
		shipping_item, far_distance_shipping_item = get_shipping_items(parsedContent)

		# check if the billing and shipping addresses are points verified from canada post.
		is_billing_cp_verified, is_shipping_cp_verified = check_if_cp_verified(parsedContent)

		logger.error(f"Billing Address Verified: {is_billing_cp_verified}, Shipping Address Verified: {is_shipping_cp_verified}")

		# Fetch detailed information for the billing and shipping addresses, considering their verification statuses.
		billing_address_detail = get_billing_address_detail(parsedContent, is_billing_cp_verified)
		shipping_address_detail = get_shipping_address_detail(parsedContent, is_shipping_cp_verified)
		logger.error(f"Billing Address Detail: {billing_address_detail}, Shipping Address Detail: {shipping_address_detail}")
  
		# Extract order details using the parsed content, province, and country information.
		order_detail = get_order_detail(parsedContent, province, country, company, shipping_item, far_distance_shipping_item,  is_billing_cp_verified)

		# Build payment details using transaction data and billing country if transactions exist. Default to None otherwise.
		payment_detail = get_payment_detail(parsedContent)
		
		# Retrieve billing and shipping address documents and customer information from the parsed content.
		billing_address_doc, shipping_address_doc, customer = get_address_and_customer(parsedContent, billing_address_detail, shipping_address_detail)
		logger.error(f"Billing Address Document: {billing_address_doc.name}")
		logger.error(f"Shipping Address Document: {shipping_address_doc.name}")
		# Create an order using the order details, customer, payment gateway, and shipping address document.
		
		order = create_order(order_detail, customer, shipping_address_doc, billing_address_doc)
		if rmq_log:
			frappe.db.set_value("RabbitMQ Orders Log", rmq_log, "sales_order", order.name, update_modified=False)
   
		continue_to_payment(order, payment_detail)
		frappe.db.commit()
  
		re_sync_rmq_order(parsedContent, order.name)
	except Exception as e:
		frappe.log_error(title='RabbitMQ Error', message=frappe.get_traceback())
		message = f"Error processing order {parsedContent['orderNumber']} from RMQ:\nSource: {parsedContent['publisher_site']}\nError: {str(e)}"
		post_to_rocket_chat([], message, rmq=True)
  
def get_shipping_items(parsedContent):
	shipping_item = None
	far_distance_shipping_item = None
	if parsedContent.get("shippingDescription"):
		is_far_distance_shipping = parsedContent.get("farDistanceCharge", False)
		total_amount = parsedContent.get("totalShipping", 0.0)
		shipping_item = get_shipping_item(parsedContent["shippingDescription"], total_amount)
		if is_far_distance_shipping:
			total_amount = parsedContent.get("farDistanceChargeAmount", 0.0)
			far_distance_shipping_item = get_shipping_item(parsedContent["shippingDescription"], total_amount, True)
			
	return shipping_item, far_distance_shipping_item
 
def create_so_usaepay(order, transaction):
    # Hold the transaction information
    frappe.get_doc({
		"doctype": "SO USAePay Transaction", 
		"order_id": order.name,
		"po_no": order.po_no,
		"transaction_key": transaction["authorizeTransactionId"] if "authorizeTransactionId" in transaction else None,
		"lead_source": order.source,
	}).insert()
    logger.error(f"USAePay transaction created for order {order.name} with transaction key {transaction['authorizeTransactionId'] if 'authorizeTransactionId' in transaction else None}")
    frappe.db.commit()
    
def continue_to_payment(order, payment_detail):
	company = order.company
	succesfull_transaction = payment_detail['transactions']
	if succesfull_transaction:
		logger.error(f"Successful Transaction Found")
		# If the payment gateway is "usaepay", create a USAePay transaction record.
		if succesfull_transaction["paymentGatewayAlias"] == "usaepay":
			create_so_usaepay(order, succesfull_transaction)
	else:
		logger.error("No successful usaepay transaction found in the parsed content.")

	# If the payment gateway is not "interacetransfer", create a payment document with payment details.
	try:
		if "paymentGatewayAlias" not in succesfull_transaction:
			logger.error(f"No paymentGatewayAlias found in the successful transaction for order {order.name}.")
			return

		if payment_detail['transactions'] and succesfull_transaction["paymentGatewayAlias"] != "interacetransfer":
			if order.neb_usaepay_transaction_key or succesfull_transaction['paymentGatewayAlias'] == 'paypalexpress':
				payment = create_payment(payment_detail, order, company, logger)
				logger.error(f"Draft payment {payment.name} created for order {order.name}")
			else:
				logger.error(f"Creating payment entry for order {order.name} from usaepay")
				process_payment_entry(succesfull_transaction, order)

		elif succesfull_transaction["paymentGatewayAlias"] == "interacetransfer":
			add_tag(order, "EtransferPaymentPending")


		frappe.db.commit()
	except Exception as e:
		frappe.log_error(title='Payment Creation Error', message=frappe.get_traceback())
		message = f"Error creating payment for order {order.name}:\nSource: {order.source}\nError: {str(e)}"
		post_to_rocket_chat([], message, rmq=True)

def get_payment_detail(parsedContent):
	payment_detail = {}

	if parsedContent.get("transactions"):
		for transaction in parsedContent['transactions']:
			if transaction.get("orderTransactionState") == 3:
				# If the transaction state is 3, it indicates a successful transaction.
				succesfull_transaction = transaction
			elif transaction.get("orderTransactionState") == 1:
				if "paymentGatewayAlias" in transaction and transaction["paymentGatewayAlias"] == "paypalexpress":
					# If the transaction state is 1 and the payment gateway is PayPal Express, consider it successful.
					succesfull_transaction = transaction

		payment_detail = {
			"transactions": succesfull_transaction,
			"billingCountry": parsedContent['billingCountry']
		}
	else:
		payment_detail = {
			"transactions": None,
			"billingCountry": parsedContent['billingCountry']
		}

	return payment_detail

def check_if_cp_verified(parsedContent):
	is_billing_cp_verified = False
	is_shipping_cp_verified = False

	# Determine if the billing address is verified, considering whether the user is logged in or a guest.
	if "BillingAddressVerification" in parsedContent:
		if parsedContent.get("accountId"):  # Logged-in user
			is_billing_cp_verified = True if parsedContent["BillingAddressVerification"]["IsVerified"] else False
		else:  # Guest user
			is_billing_cp_verified = True if parsedContent["GuestBillingAddressVerification"]["IsVerified"] else False

	# Determine if the shipping address is verified, considering whether the user is logged in or a guest.
	if "ShippingAddressVerification" in parsedContent:
		if parsedContent.get("accountId"):  # Logged-in user
			is_shipping_cp_verified = True if parsedContent["ShippingAddressVerification"]["IsVerified"] else False
		else:  # Guest user
			is_shipping_cp_verified = True if parsedContent["GuestShippingAddressVerification"]["IsVerified"] else False
   
	return is_billing_cp_verified, is_shipping_cp_verified

def process_payment_entry(transaction, order):
	from metactical.custom_scripts.usaepay.usaepay_api import get_usaepay_order_detail
	try:
		# get transaction details from USAePay and create payment entry
		get_usaepay_order_detail(transaction, order, logger)
	except Exception as e:
		frappe.log_error(title='Payment Entry Processing Error', message=frappe.get_traceback())
		post_to_rocket_chat([], f"Unable to process payment entry for order {order.name}: {str(e)}", rmq=True)
  
def add_tag(order, tag):
	if frappe.db.exists("Tag", tag):
		try:
			tag_link = frappe.get_doc({
				"doctype": "Tag Link",
				"tag": tag,
				"document_type": "Sales Order",
				"document_name": order.name
			})
			tag_link.insert()
			frappe.db.commit()
			logger.error(f"Tag {tag_link.tag} linked to order {order.name}")
		except Exception as e:
			frappe.log_error(title='Tag Link Error', message=frappe.get_traceback())
			post_to_rocket_chat([], f"Unable to link tag {tag} to order {order.name}: {str(e)}", rmq=True)
	
# This method retrieves or creates billing and shipping addresses, as well as the associated customer.
# It checks for existing addresses and customers in the system. If none are found, it creates new ones.
# The method returns the billing address document, shipping address document, and customer record.
def get_address_and_customer(parsedContent, billing_address_detail, shipping_address_detail):
	# Check if a billing address already exists in the system.
	existing_billing_address = check_existing_address(billing_address_detail, "Billing")
		
	customer = get_or_create_customer(
		parsedContent['publisher_site'], 
		billing_address_detail
	)
 
	logger.error(f"Customer: {customer}")
 
	if existing_billing_address:
		logger.error(f"Existing Billing Address Found: {existing_billing_address}")
		# If an existing billing address is found, fetch its document.
		billing_address_doc = frappe.get_doc("Address", existing_billing_address)
	else:
		billing_address_doc = create_address(billing_address_detail, customer, "Billing")
		logger.error(f"Created New Billing Address: {billing_address_doc.name}")

	existing_shipping_address = check_existing_address(shipping_address_detail, "Shipping")
	if existing_shipping_address:
		logger.error(f"Existing Shipping Address Found: {existing_shipping_address}")
		# If an existing shipping address is found, fetch its document.
		shipping_address_doc = frappe.get_doc("Address", existing_shipping_address)
	else:
		# If no shipping address is found, create a new one.
		shipping_address_doc = create_address(shipping_address_detail, customer, "Shipping")
		logger.error(f"Created New Shipping Address: {shipping_address_doc.name}")

	# Return the billing address document, shipping address document, and th
	return billing_address_doc, shipping_address_doc, customer

# extract order details from the parsed content
def get_order_detail(parsedContent, province, country, company, shipping_item, far_distance_shipping_item, is_billing_cp_verified):
	return {
		"order_id": parsedContent['orderNumber'],
		"order_date": parsedContent['orderDate'], 
		"items": parsedContent['items'],
		"discounts": parsedContent['Discounts'],
		"total_value": parsedContent['totalValueAmount'], 
		"total_shipping_amount": parsedContent['totalShippingAmount'] if "totalShippingAmount" in parsedContent else 0.0,
		"total_discount_amount": parsedContent['TotalDiscount'] if "TotalDiscount" in parsedContent else 0.0,
		"source": parsedContent['publisher_site'],
		"taxes_and_charges": get_taxes_and_charges(province, country, company, parsedContent['publisher_site']),
		"currency": parsedContent['grandTotalAmount']['Currency']["isoCode"],
		"company": company,
		"shipping_item": shipping_item,
		"far_distance_shipping_item": far_distance_shipping_item,
		"signifyd": parsedContent.get("SignifyD", None) if "SignifyD" in parsedContent else None,
		"is_cp_verified": is_billing_cp_verified,
		"ifw_store_pickup": parsedContent["PickInLocation"]
	}

# extract billing address details from the parsed content
def get_billing_address_detail(parsedContent, is_cp_verified):
	return {
		"first_name": parsedContent['billingFirstName'],
		"last_name": parsedContent['billingLastName'],
		"email": parsedContent['billingEmail'] if parsedContent.get("billingEmail") else None,
		"company": parsedContent['billingOrganization'] if parsedContent.get("billingOrganization") else None,
		"phone": parsedContent['billingPhoneNumber'] if parsedContent.get("billingPhoneNumber") else None,
		"line1": parsedContent['billingLine1'] if parsedContent.get("billingLine1") else None,
		"line2": parsedContent['billingLine2'] if parsedContent.get("billingLine2") else None,
		"city": parsedContent['billingCity'] if parsedContent.get("billingCity") else None,
		"region_code": parsedContent['billingRegionCode'] if parsedContent.get("billingRegionCode") else None,
		"postal_code": parsedContent['billingPostalCode'] if parsedContent.get("billingPostalCode") else None,
		"state": parsedContent['billingRegion']['name'] if parsedContent.get("billingRegion") else None,
		"country": parsedContent['billingCountry']['name'] if parsedContent.get("billingCountry") else None,
		"currency": parsedContent['grandTotalAmount']['Currency']["isoCode"] if parsedContent.get("grandTotalAmount") else None,
		"account_id": parsedContent['accountId'] if "accountId" in parsedContent else None,
		"postal_code": parsedContent['billingPostalCode'] if parsedContent.get("billingPostalCode") else None,
		"is_cp_verified": is_cp_verified
	}

# extract shipping address details from the parsed content
def get_shipping_address_detail(parsedContent, is_cp_verified):
	return  {
		"first_name": parsedContent['shippingFirstName'],
		"last_name": parsedContent['shippingLastName'],
		"email": parsedContent['shippingEmail'] if parsedContent.get("shippingEmail") else None,
		"company": parsedContent['shippingOrganization'] if parsedContent.get("shippingOrganization") else None,
		"phone": parsedContent['shippingPhoneNumber'] if parsedContent.get("shippingPhoneNumber") else None,
		"line1": parsedContent['shippingLine1'] if parsedContent.get("shippingLine1") else None,
		"line2": parsedContent['shippingLine2'] if parsedContent.get("shippingLine2") else None,
		"city": parsedContent['shippingCity'] if parsedContent.get("shippingCity") else None,
		"region_code": parsedContent['shippingRegionCode'] if parsedContent.get("shippingRegionCode") else None,
		"postal_code": parsedContent['shippingPostalCode'] if parsedContent.get("shippingPostalCode") else None,
		"state": parsedContent['shippingRegion']['name'] if parsedContent.get("shippingRegion") else None,
		"country": parsedContent['shippingCountry']['name'] if parsedContent.get("shippingCountry") else None,
		"currency": parsedContent['grandTotalAmount']['Currency']["isoCode"] if parsedContent.get("grandTotalAmount") else None,
		"account_id": parsedContent['accountId'] if "accountId" in parsedContent else None,
		"postal_code": parsedContent['shippingPostalCode'] if parsedContent.get("shippingPostalCode") else None,
		"is_cp_verified": is_cp_verified
	}

# 
def get_shipping_item(shipping_quote, total, is_far_distance_shipping=False):
	shipping_item = ""
	if is_far_distance_shipping:
		shipping_item = "Far Distance Charge"
	else:
		if shipping_quote == "Flat Rate Shipping - Standard Shipping" or shipping_quote == "Flat Rate Shipping - Standard":
			shipping_item = "Shipping"
		elif shipping_quote == "Flat Rate Shipping - Express Shipping":
			shipping_item = "Express Shipping"

	if not shipping_item:
		return None

	shipping_item_code = frappe.db.get_value("Item", {"item_name": shipping_item}, "item_code")
	if not shipping_item_code:
		return None

	return {
		"item_code": shipping_item_code,
		"qty": 1,
		"rate": total
	}


def get_or_create_customer(lead_source, billing_address_detail):
	# If a billing address document exists, attempt to find an existing customer based on it.
	customer = None
	if billing_address_detail:
		existing_customer = check_existing_customer(billing_address_detail)
		logger.error(f"Found Existing Customer: {existing_customer}")

	if existing_customer and frappe.db.exists("Customer", existing_customer):
		customer = frappe.get_doc("Customer", existing_customer)
  
	if not customer:
		# Create a new Customer record in the system using billing address details.
		customer = frappe.get_doc({
			"doctype": "Customer",
			"first_name": billing_address_detail['first_name'],  # Customer's first name
			"last_name": billing_address_detail['last_name'],    # Customer's last name
			"customer_name": billing_address_detail['first_name'] + " " + billing_address_detail['last_name'],  # Full name
			"territory": billing_address_detail['state'],  # Country as the territory
			# Default price list is fetched from the Lead Source; if not available, fallback to "RET - Camo".
			"default_price_list": frappe.db.get_value("Lead Source", lead_source, "custom_neb_price_list") or "RET - Camo",
			"billing_currency": billing_address_detail['currency'],  # Customer's billing currency
			"posa_referral_code": billing_address_detail['account_id'],  # Referral code from billing details
			"pincode": billing_address_detail['postal_code'],  # Customer's postal code
		})

		# Insert the new Customer record into the database.
		customer.insert()
		logger.error(f"Created New Customer: {customer.name}")

	# Create a Contact record for the Customer using their billing details.
	contact = create_contact(billing_address_detail, customer.name)

	# Commit the changes to the database to save the new Customer and Contact records.
	frappe.db.commit()

	# Return the name of the newly created Customer.
	return customer.name

def check_existing_customer(billing_address_detail):
    customer = frappe.db.sql("""
		SELECT `tabCustomer`.name FROM `tabCustomer`
		JOIN `tabDynamic Link` ON `tabCustomer`.name = `tabDynamic Link`.link_name
		JOIN `tabAddress` ON `tabDynamic Link`.parent = `tabAddress`.name
		WHERE `tabDynamic Link`.link_doctype = 'Customer' AND
		`tabAddress`.address_type = 'Billing' AND
		`tabAddress`.ifw_first_name = %s AND
		`tabAddress`.phone = %s AND
		`tabAddress`.pincode = %s AND
		`tabAddress`.address_line1 = %s
		order by `tabCustomer`.modified desc
	""", (billing_address_detail['first_name'], billing_address_detail['phone'], billing_address_detail['postal_code'], billing_address_detail['line1']), as_dict=True)
    
    if customer:
        return customer[0].name
    return None

def create_order(order_detail, customer, shipping_address_doc, billing_address_doc):
	logger.error(f"Creating order for customer: {customer}, Order ID: {order_detail['order_id']}")
	items = process_items(order_detail['items'], order_detail=order_detail)

	order_data = {
		"doctype": "Sales Order",
		"customer": customer,
		"order_type": "Shopping Cart",
		"po_date": remove_tz_from_date(order_detail['order_date']),
		"po_no": order_detail["order_id"],
		"items": items,
		"source": order_detail['source'],
		"taxes_and_charges": order_detail['taxes_and_charges'],
		"delivery_date": calculate_delivery_date(order_detail['order_date']),
		"total_value": order_detail['total_value'],
		"total_shipping_amount": order_detail['total_shipping_amount'],
		"total_discount_amount": order_detail['total_discount_amount'],
		"currency": order_detail['currency'],
		"transaction_date": remove_tz_from_date(order_detail['order_date']),
		"company": order_detail['company'],
		"company_address": frappe.db.get_value("Lead Source", order_detail['source'], "neb_company_address"),
		"mena_is_cp_verified": order_detail["is_cp_verified"],
		"shipping_address_name": shipping_address_doc.name,
		"customer_address": billing_address_doc.name,
		"ifw_store_pickup": order_detail["ifw_store_pickup"],
		"discount_amount": order_detail["total_discount_amount"],
		"ignore_pricing_rule": 1,  # Ignore pricing rules for this order
		"is_rush": is_rush(items),
		"apply_discount_on": "Net Total"
	}
 
	if order_detail.get("signifyd"):
		order_data.update({
			"ifw_signifyd_sid": order_detail['signifyd'].get('Sid'),
			"ifw_signifyd_caseid": order_detail['signifyd'].get('CaseId'),
			"ifw_signifyd_casestatus": order_detail['signifyd'].get('CaseStatus'),
			"ifw_signifyd_approved": order_detail['signifyd'].get('IsApproved'),
			"ifw_signifyd_score": order_detail['signifyd'].get('Score'),
			"ifw_signifyd_guaranteedisposition": order_detail['signifyd'].get('GuarenteedDisposition'),
			"ifw_signifyd_fulfilled": order_detail['signifyd'].get('Fullfilled'),
		})
 
	new_order = frappe.get_doc(order_data)

	# set the missing values for the order and submit it if the gateway is not "interacetransfer"
	new_order.set_missing_values()	
	new_order.save()
	logger.error(f"New Order Created: {new_order.name} shipping address: {shipping_address_doc.name}, billing address: {billing_address_doc.name}")
	frappe.db.commit()
	
	new_order.submit()
	frappe.db.commit()
 
	logger.error(f"Order {new_order.name} Submitted. Shipping Address: {shipping_address_doc.name}, Billing Address: {billing_address_doc.name}")

	order = frappe.get_doc("Sales Order", new_order.name)
	if order.shipping_address_name != shipping_address_doc.name:
		order.shipping_address_name = shipping_address_doc.name
		order.customer_address = billing_address_doc.name
		order.save()
		logger.error(f"Order {new_order.name} updated with correct addresss: Shipping Address: {shipping_address_doc.name}, Billing Address: {billing_address_doc.name}")
		frappe.db.commit()

	return new_order

def is_rush(items):
    for item in items:
        if item.get("item_code") == "99992":
            return True
    return False

def create_address(address_detail, customer, address_type):
	address = frappe.get_doc({
		"doctype": "Address",
		"title": address_detail["first_name"] + " " + address_detail["last_name"],
		"ifw_first_name": address_detail["first_name"],
		"ifw_last_name": address_detail["last_name"] if "last_name" in address_detail else "",
		"email_id": address_detail["email"],
		"phone": address_detail["phone"],
		"company": address_detail["company"],
		"address_type": address_type,
		"address_line1": address_detail["line1"],
		"address_line2": address_detail["line2"],
		"city": address_detail["city"],
		"state": address_detail["state"],
		"country": address_detail["country"],
		"pincode": address_detail["postal_code"],
		"mena_is_cp_verified": address_detail["is_cp_verified"]
	})

	dynamic_link = frappe.new_doc("Dynamic Link")
	dynamic_link.update({
		"link_doctype": "Customer",
		"link_name": customer
	})

	address.links.append(dynamic_link)

	address.insert()
	frappe.db.commit()

	return address

# check if an address already exists in the system
def check_existing_address(address_detail, address_type):
	logger.error(f"Checking for existing address: {address_detail['first_name']} {address_detail['last_name']}, Phone: {address_detail['phone']}, Address Type: {address_type}, Postal Code: {address_detail['postal_code']}, State: {address_detail['line1']}")
	existing_address = frappe.db.sql("""
		SELECT name 
		FROM `tabAddress`
		WHERE ifw_first_name = %s
		AND phone = %s
		AND address_type = %s
		AND pincode = %s
		AND address_line1 = %s
		ORDER BY modified DESC
	""", 
		(
			address_detail['first_name'], 
			address_detail['phone'], 
			address_type, 
			address_detail['postal_code'], 
			address_detail['line1']
		),
		as_dict=True
	)

	if existing_address:
		logger.error(f"Found existing address: {existing_address[0].name}")
		return existing_address[0].name
	else:
		logger.error("No existing address found.")
		return None

def create_contact(contact_detail, customer):
	check_existing = frappe.db.sql("""
		SELECT name FROM `tabContact`
		WHERE email_id = %s
		AND phone = %s
		AND first_name = %s
		AND last_name = %s
		order by modified desc
	""", 
		(
			contact_detail["email"], 
			contact_detail["phone"], 
			contact_detail["first_name"], 
			contact_detail["last_name"]
		), as_dict=True
	)
 	
	if check_existing:
		check_existing = check_existing[0].name
		logger.error(f"Found a contact {check_existing} with email {contact_detail['email']} and phone {contact_detail['phone']}.")
		# check if the contact is linked with the customer
		if frappe.db.exists("Dynamic Link", {"link_doctype": "Customer", "link_name": customer, "parent": check_existing}):
			logger.error(f"Contact {check_existing} already exists and is linked to customer {customer}.")
			return check_existing
		else:
			contact = frappe.get_doc("Contact", check_existing)
			dynamic_link = frappe.new_doc("Dynamic Link")
			dynamic_link.update({
				"link_doctype": "Customer",
				"link_name": customer
			})
   
			contact.links.append(dynamic_link)
			contact.save()
			frappe.db.commit()
   
			logger.error(f"Contact {contact.name} updated with customer link.")
			return contact.name
	else:
		contact = frappe.get_doc({
			"doctype": "Contact",
			"first_name": contact_detail["first_name"],
			"last_name": contact_detail["last_name"],
			"email_id": contact_detail["email"],
			"phone": contact_detail["phone"],
			"customer": customer,
			"is_primary_contact": 1
		})

		# add the default email address
		contact_email = frappe.new_doc("Contact Email")
		contact_email.update({
			"email_id": contact_detail["email"],
			"is_primary": 1
		})

		contact.append("email_ids", contact_email)
  
		# add the default phone number
		contact_phone = frappe.new_doc("Contact Phone")
		contact_phone.update({
			"phone": contact_detail["phone"],
			"is_primary_phone": 1,
			"is_primary_mobile_no": 1
		})
		contact.append("phone_nos", contact_phone)

		# link the contact to the customer
		dynamic_link = frappe.new_doc("Dynamic Link")
		dynamic_link.update({
			"link_doctype": "Customer",
			"link_name": customer
		})

		contact.links.append(dynamic_link)

		# save the contact
		contact.insert()
  
		logger.error(f"Created new contact: {contact.name} for customer {customer}.")
		frappe.db.commit()

		return contact.name

# This method processes a list of items and creates corresponding "Sales Order Item" documents.
# For each item in the input list, it generates a new Sales Order Item with the provided details (SKU, quantity, unit price, and warehouse).
# If a shipping item is provided, it also creates a Sales Order Item for the shipping charges.
# Finally, it returns a list of all the created Sales Order Item documents.
def create_payment(payment_detail, order, company, logger= None):
	try:
		if logger:
			logger.error(f"Creating payment for order {order.name}")
	
		if not payment_detail:
			frappe.log_error(title='Payment Detail Error', message=f'{order.name} does not have payment details.')
			return None

		transaction_detail = payment_detail['transactions']
	
		if transaction_detail.get("paymentGatewayAlias") == "paypalexpress":
			country = frappe.db.get_value("Company", company, "country")
			if country == "Canada":
				card_type = "PayPal - CAD"
			else:
				card_type = "PayPal - USD"
		else:
			card_type = get_card_type(payment_detail)

		new_payment = get_payment_entry(order.doctype, order.name)
		new_payment.mode_of_payment = card_type

		account = get_bank_cash_account(company=company, mode_of_payment=card_type)
		new_payment.paid_to = account["account"]
		new_payment.paid_amount = transaction_detail["amount"]
		new_payment.reference_no = order.neb_usaepay_transaction_key
		new_payment.reference_date = remove_tz_from_date(payment_detail['transactions']["createdOn"])
		new_payment.save()

		can_be_submitted = True
		if transaction_detail.get("paymentGatewayAlias") == "paypalexpress" and transaction_detail.get("orderTransactionState") == 1:
			can_be_submitted = False
      
		if can_be_submitted:
			new_payment.submit()
		frappe.db.commit()

		if logger:
			logger.error(f"Payment created for order {order.name} with mode of payment {new_payment.mode_of_payment} and amount {new_payment.paid_amount}")

		return new_payment
	except Exception as e:
		frappe.log_error(title='Payment Creation Error', message=frappe.get_traceback())


def get_card_type(payment_detail):
	card_type = "Visa"
	creditcard_type = payment_detail['transactions']["creditCardTypeId"]
	billing_country = payment_detail["billingCountry"]["name"]

	if creditcard_type == "e5d2155d-81f4-11e2-9e96-0800200c9a66":
		# if billing_country == "Canada":
		card_type = "Master Card"
		# else:
		# 	card_type = "Master Card - USD"
			
	elif creditcard_type == "e5d2155e-81f4-11e2-9e96-0800200c9a66":
		# if billing_country == "Canada":
		card_type = "Visa"
		# else:
		# 	card_type = "Visa - USD"
	elif creditcard_type == "e5d2155f-81f4-11e2-9e96-0800200c9a66":
		# if billing_country == "Canada":
		card_type = "Amex"
		# else:
			# card_type = "Amex - USD"
	
	return card_type

def calculate_delivery_date(order_date):
	day = frappe.utils.getdate(order_date).strftime("%A")
	if day == "Friday":
		return frappe.utils.add_to_date(order_date, days=3)
	elif day == "Saturday":
		return frappe.utils.add_to_date(order_date, days=2)

	return frappe.utils.add_to_date(order_date, days=1)

def get_taxes_and_charges(province, country, company=None, lead_source=None):
	company_code = frappe.db.get_value("Company", company, "abbr")
	if province == "Texas":
		return f"Texas - {company_code}"
	elif province == "Alberta":
		return "Alberta - ICL"
	elif province == "British Columbia" and lead_source != "Website - GPD":
		return "British Columbia - ICL"
	elif province == "British Columbia" and lead_source == "Website - GPD":
		return "British Columbia - GST Only - ICL"
	elif province == "Manitoba":
		return "Manitoba - ICL"
	elif province == "New Brunswick":
		return "New Brunswick - ICL"
	elif province == "Newfoundland and Labrador":
		return "Newfoundland and Labrador - ICL"
	elif province == "Nova Scotia":
		return "Nova Scotia - ICL"
	elif province == "Ontario":
		return "Ontario - ICL"
	elif province == "Prince Edward Island":
		return "Prince Edward Island - ICL"
	elif province == "Quebec" and lead_source != "Website - GPD":
		return "Quebec GST and QST - ICL"
	elif province == "Quebec" and lead_source == "Website - GPD":
		return "Quebec - GST - ICL"
	elif province == "Saskatchewan":
		return "Saskatchewan - ICL"
	elif province == "Northwest Territories":
		return "Northwest Territories - ICL"
	elif province == "Nunavut":
		return "Nunavut - ICL"
	elif province == "Yukon" or province == "Yukon Territory":
		return "Yukon - ICL"
	elif country == "United States":
		return "United States - " + company_code
	else:
		return province + " - " + company_code if company_code else province + " - ICL"
		
def process_items(items, order_detail):
	items_list = []
	warehouse = frappe.db.get_value("Lead Source", order_detail['source'], "neb_default_warehouse") or "W01-WHS-Active Stock - ICL"
	
	for item in items:
		if item['isTrashed']:
			continue

		item_code = frappe.db.get_value("Item", {"ifw_retailskusuffix": item['retailSku']}, "name")
		if not item_code:
			frappe.throw(f"Item with retail SKU {item['retailSku']} not found for order {order_detail['order_id']}")

		new_item = frappe.get_doc({
			"doctype": "Sales Order Item",
			"item_code": item_code,
			"qty": item['quantity'],
			"price_list_rate": item['unitPrice'],
			"warehouse": warehouse
		})

		items_list.append(new_item)

	shipping_item = order_detail['shipping_item']
	if shipping_item:
		new_shipping_item = frappe.get_doc({
			"doctype": "Sales Order Item",
			"item_code": shipping_item['item_code'],
			"qty": shipping_item['qty'],
			"price_list_rate": shipping_item['rate'],
			"warehouse": warehouse
		})  
		items_list.append(new_shipping_item)
  
	if order_detail['far_distance_shipping_item']:
		far_distance_shipping_item = order_detail['far_distance_shipping_item']
		new_far_distance_shipping_item = frappe.get_doc({
			"doctype": "Sales Order Item",
			"item_code": far_distance_shipping_item['item_code'],
			"qty": far_distance_shipping_item['qty'],
			"price_list_rate": far_distance_shipping_item['rate'],
			"warehouse": warehouse
		})
		items_list.append(new_far_distance_shipping_item)

	return items_list

def update_signify_detail(parsedContent):    
	try:
		sales_order = frappe.db.get_value("Sales Order", {"ifw_signifyd_sid": parsedContent['Sid']}, "name")
		if sales_order:
			frappe.db.set_value("Sales Order", sales_order, {
				"ifw_signifyd_caseid": parsedContent['CaseId'] if parsedContent.get('CaseId') else None,
				"ifw_signifyd_casestatus": parsedContent['CaseStatus'] if parsedContent.get('CaseStatus') else None,
				"ifw_signifyd_score": parsedContent['Score'] if parsedContent.get('Score') else None,
				"ifw_signifyd_approved": parsedContent['IsApproved'] if parsedContent.get('IsApproved') else False,
				"ifw_signifyd_guaranteedisposition": parsedContent['GuarenteedDisposition'] if parsedContent.get('GuarenteedDisposition') else None,
				"ifw_signifyd_fulfilled": parsedContent['Fullfilled'] if parsedContent.get('Fullfilled') else None,
			}, update_modified=False)
			frappe.db.commit()
		else:
			frappe.log_error(title='SignifyD Update Error', message=f"Sales Order not found for SignifyD SID: {parsedContent['Sid']}")
	except Exception as e:
		frappe.log_error(title='SignifyD Update Error', message=frappe.get_traceback())
		message = f"Unable to update SignifyD details for SID {parsedContent['Sid']}: {str(e)}"
		post_to_rocket_chat([], message, rmq=True)
  
def create_rmq_log(parsedContent):
	try:
		publisher_site = parsedContent.get("publisher_site", "Unknown")	
		rmq_log = frappe.get_doc({
			"doctype": "RabbitMQ Orders Log",
			"payload": as_unicode(parsedContent),
			"lead_source": publisher_site
		})
  
		rmq_log.insert()		
		frappe.db.commit()
		return rmq_log.name
	except Exception as e:
		frappe.log_error(title='RMQ Log Creation Error', message=frappe.get_traceback())

def as_unicode(text: str, encoding: str = "utf-8") -> str:
	"""Convert to unicode if required"""
	if isinstance(text, str):
		return text
	elif text is None:
		return ""
	elif isinstance(text, bytes):
		return str(text, encoding)
	else:
		return str(text)

def re_sync_rmq_order(parsedContent, sales_order=None):
	try:
		logger.error("\n\n")
		# Parse the content of the document to extract order details.
		if type(parsedContent) is str:
			doc = frappe.get_doc("RabbitMQ Orders Log", parsedContent)
			parsedContent = parse_dict_str(doc.payload)
   
		# parsedContent = json.loads(doc.payload)
		logger.error(f"Re-Processing Order: {parsedContent['orderNumber']}")

		order_number = parsedContent.get("orderNumber")
		source = parsedContent.get("publisher_site", "Unknown")
		sales_order = frappe.db.exists("Sales Order", {"po_no": order_number, "source": source})

		if sales_order:
			sales_order_doc = frappe.get_doc("Sales Order", sales_order)
			logger.error(f"Found existing Sales Order: {sales_order_doc.name} for order number {order_number}.")
			# If the order already exists, update the SignifyD details

			is_billing_cp_verified, is_shipping_cp_verified = check_if_cp_verified(parsedContent)
			verify_contact(parsedContent, sales_order_doc, is_billing_cp_verified)
			sales_order_doc.reload()
   
			so_billing_address = frappe.get_doc("Address", sales_order_doc.customer_address)   
			so_shipping_address = frappe.get_doc("Address", sales_order_doc.shipping_address_name)

			billing_address_doc, shipping_address_doc, customer = get_address_and_customer(
				parsedContent, 
				get_billing_address_detail(parsedContent, is_billing_cp_verified), 
				get_shipping_address_detail(parsedContent, is_shipping_cp_verified)
			)
   
			verify_address(billing_address_doc, so_billing_address, sales_order_doc)
			sales_order_doc.reload()
			verify_address(shipping_address_doc, so_shipping_address, sales_order_doc)
			sales_order_doc.reload()
   
			verify_items(parsedContent, sales_order_doc)
			sales_order_doc.reload()

			verify_payment(parsedContent, sales_order_doc, billing_address_doc)
   
			delivery_date = sales_order_doc.delivery_date
			is_rush = sales_order_doc.is_rush
			
		else:
			logger.error(f"No existing Sales Order found for order number {order_number}. Proceeding with re-sync.")
			print(f"No existing Sales Order found for order number {order_number}. Proceeding with re-sync.")
			process_rmq_data(parsedContent)
		
		# # Extract province and country information from the parsed content.
	except Exception as e:
		print(f"Error parsing RMQ content: {e}")
		frappe.log_error(title='RabbitMQ Parsing Error', message=frappe.get_traceback())
  
def parse_dict_str(dict_str):
	try:
		py_dict = ast.literal_eval(dict_str)

		return py_dict
	except Exception as e:
		raise ValueError(f"Could not parse string: {e}")

def verify_contact(parsedContent, sales_order, is_billing_cp_verified=False):
	"""
	This function verifies the contact details against the parsed content.
	It updates the contact's email and phone number if they differ from the parsed content.
	"""
	
	billing_address_detail = get_billing_address_detail(parsedContent, is_billing_cp_verified)
	contact = create_contact(billing_address_detail, sales_order.customer)
 
	if contact != sales_order.contact_person:
		logger.error(f"Contact {contact} does not match Sales Order {sales_order.name}. Updating from {sales_order.contact_person}.")
		frappe.db.set_value("Sales Order", sales_order.name, "contact_person", contact, update_modified=False)
		frappe.db.commit()
 
def verify_address(address_doc, so_address, sales_order):
	if address_doc.name != so_address.name:
		if address_doc.address_type == "Billing":
			sales_order.customer_address = address_doc.name
		elif address_doc.address_type == "Shipping":
			sales_order.shipping_address_name = address_doc.name

		sales_order.save()

		frappe.db.commit()
	else:
		logger.error(f"No discrepancies found in {address_doc.address_type} for Sales Order {sales_order.name}. No update needed.")
  
def verify_items(parsedContent, sales_order):
	"""
	This function verifies the items in the Sales Order against the parsed content.
	It updates the items in the Sales Order if they differ from the parsed content.
	"""
	shipping_item, far_distance_shipping_item = get_shipping_items(parsedContent)
	order_detail = get_order_detail(parsedContent, 
		parsedContent.get("billingRegion", {}).get("name"), 
		parsedContent.get("billingCountry", {}).get("name"), 
		sales_order.company, 
		shipping_item, 
		far_distance_shipping_item,
		sales_order.mena_is_cp_verified
	)

	items = process_items(order_detail['items'], order_detail=order_detail)
	items_updated = False

	so_item_row = {}
	for i, item in enumerate(sales_order.items):
		if item.item_code != items[i].item_code or item.qty != items[i].qty or item.price_list_rate != round(items[i].price_list_rate, 2):
			items_updated = True

		so_item_row[item.item_code] = item

	if items_updated:
		trans_items = get_items_list_to_update(so_item_row, items)
		trans_items = json.dumps(trans_items)
		update_child_qty_rate(parent_doctype="Sales Order", parent_doctype_name=sales_order.name, trans_items=trans_items, child_docname="items")

		frappe.db.commit()
  
def get_items_list_to_update(so_item_row, items):
	updated_item_row = []
	for i, item in enumerate(items):
		if so_item_row.get(item.item_code):
			row = so_item_row[item.item_code]
			item_row = {
				"name": row.name,
				"docname": row.name,
				"item_code": row.item_code,
				"conversion_factor": row.conversion_factor,
				"qty": item.qty,
				"price_list_rate": row.price_list_rate,
				"uom": row.uom,
				"picked_qty": row.picked_qty,
				"warehouse": row.warehouse,
				"delivered_qty": row.delivered_qty,
				"idx": i+1
			}
		else:
			item_row = {
				"item_code": item.item_code,
				"conversion_factor": 1,
				"qty": item.qty,
				"price_list_rate": item.price_list_rate,
				"idx": i+1
			}
   
		updated_item_row.append(item_row)

	return updated_item_row

def verify_payment(parsedContent, sales_order, billing_address_doc):
	per_billed = sales_order.per_billed or 0
	advance_paid = sales_order.advance_paid or 0
 
	draft_payment_entry = frappe.db.sql("""
		SELECT `tabPayment Entry`.name FROM `tabPayment Entry`
		Join `tabPayment Entry Reference` ON `tabPayment Entry`.name = `tabPayment Entry Reference`.parent
		WHERE `tabPayment Entry`.docstatus = 0 AND reference_doctype = 'Sales Order' AND reference_name = %s
		order by `tabPayment Entry`.modified desc
	""", (sales_order.name,), as_dict=True)
 
	if not per_billed and not advance_paid and not len(draft_payment_entry):
		payment_detail = get_payment_detail(parsedContent)
		continue_to_payment(sales_order, payment_detail)
	elif draft_payment_entry:
		logger.error(f"Payment already exists for Sales Order {sales_order.name}. Skipping payment creation.")
		if draft_payment_entry:
			logger.error(f"Draft Payment Entry found: {draft_payment_entry[0].name} for Sales Order {sales_order.name}.")
	else:
		logger.error(f"Payment entry exists for Sales Order {sales_order.name}")