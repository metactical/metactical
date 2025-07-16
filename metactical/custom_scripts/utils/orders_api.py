import frappe
from metactical.custom_scripts.utils.metactical_utils import remove_tz_from_date, post_to_rocket_chat
from metactical.custom_scripts.payment_entry.payment_entry import get_payment_entry
from erpnext.accounts.doctype.sales_invoice.sales_invoice import get_bank_cash_account
from erpnext.accounts.doctype.payment_entry.payment_entry import get_account_details

def receive_rmq_data(parsedContent):
	try:
		# from metactical.custom_scripts.utils.loggedinuser4 import parsedContent
		rmq_log = create_rmq_log(parsedContent)
		
		# Assign the shipping province and country based on the parsed content.
		# If not provided, default to "Alberta" for the province and "Canada" for the country.
		province = parsedContent['shippingRegion']['name'] if parsedContent.get("shippingRegion") else "Alberta"
		country = parsedContent['shippingCountry']['name'] if parsedContent.get("shippingCountry") else "Canada"
		frappe.form_dict["account"] = ""

		# Retrieve the default company name from the Global Defaults doctype in Frappe.
		
		company = frappe.db.get_value("Lead Source", parsedContent["publisher_site"], "neb_company") or frappe.db.get_single_value("Global Defaults", "default_company")  
  
		# Initialize the shipping item as None. If a shipping description exists,
		# use it to fetch the corresponding shipping item and cost.
		shipping_item = None
		if parsedContent.get("shippingDescription"):
			shipping_item = get_shipping_item(parsedContent["shippingDescription"], parsedContent["totalShipping"])

		# check if the billing and shipping addresses are points verified from canada post.
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

		# Fetch detailed information for the billing and shipping addresses, considering their verification statuses.
		billing_address_detail = get_billing_address_detail(parsedContent, is_billing_cp_verified)
		shipping_address_detail = get_shipping_address_detail(parsedContent, is_shipping_cp_verified)

		# Extract order details using the parsed content, province, and country information.
		order_detail = get_order_detail(parsedContent, province, country, company, shipping_item, is_billing_cp_verified)

		# Build payment details using transaction data and billing country if transactions exist. Default to None otherwise.
		succesfull_transaction = None
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

		# Retrieve billing and shipping address documents and customer information from the parsed content.
		billing_address_doc, shipping_address_doc, customer = get_address_and_customer(parsedContent, billing_address_detail, shipping_address_detail)

		# Create an order using the order details, customer, payment gateway, and shipping address document.
		order = create_order(order_detail, customer, shipping_address_doc, billing_address_doc)
		if rmq_log:
			frappe.db.set_value("RabbitMQ Orders Log", rmq_log, "sales_order", order.name, update_modified=False)

		# If the payment gateway is not "interacetransfer", create a payment document with payment details.
		try:
			if "paymentGatewayAlias" not in succesfull_transaction:
				return
			
			if payment_detail['transactions'] and succesfull_transaction["paymentGatewayAlias"] != "interacetransfer":
				if order.neb_usaepay_transaction_key or succesfull_transaction['paymentGatewayAlias'] == 'paypalexpress':
					payment = create_payment(payment_detail, order, company)
				else:
					from metactical.custom_scripts.sales_order.sales_order import get_transaction_key
					transaction_key = get_transaction_key(order.source, order.po_no, order.customer)
					if transaction_key:
						frappe.db.set_value("Sales Order", order.name, "neb_usaepay_transaction_key", transaction_key, update_modified=False)
						payment = create_payment(payment_detail, order, company)
      
			elif succesfull_transaction["paymentGatewayAlias"] == "interacetransfer":
				add_tag(order, "EtransferPaymentPending")
    
			frappe.db.commit()
		except Exception as e:
			frappe.log_error(title='Payment Creation Error', message=frappe.get_traceback())
			post_to_rocket_chat([], f"Unable to create payment for order {order.name}: {str(e)}", rmq=True)
	except Exception as e:
		frappe.log_error(title='RabbitMQ Error', message=frappe.get_traceback())
		post_to_rocket_chat([], f"Unable to process order from RMQ: {str(e)}", rmq=True)

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
		except Exception as e:
			frappe.log_error(title='Tag Link Error', message=frappe.get_traceback())
			post_to_rocket_chat([], f"Unable to link tag {tag} to order {order.name}: {str(e)}", rmq=True)
	
# This method retrieves or creates billing and shipping addresses, as well as the associated customer.
# It checks for existing addresses and customers in the system. If none are found, it creates new ones.
# The method returns the billing address document, shipping address document, and customer record.
def get_address_and_customer(parsedContent, billing_address_detail, shipping_address_detail):
	# Check if a billing address already exists in the system.
	existing_billing_address = check_existing_address(billing_address_detail, "Billing")
	customer = None

	if existing_billing_address:
		# If an existing billing address is found, fetch its document.
		billing_address_doc = frappe.get_doc("Address", existing_billing_address)

		# Retrieve or create a customer associated with the billing address.
		customer = get_or_create_customer(parsedContent['publisher_site'], billing_address_detail, shipping_address_detail, billing_address_doc)
	else:
		# If no billing address is found, create a new customer and billing address.
		customer = get_or_create_customer(parsedContent['publisher_site'], billing_address_detail, shipping_address_detail)
		billing_address_doc = create_address(billing_address_detail, customer, "Billing")

	# if same address is used for billing and shipping, return the billing address as the shipping address
	if not parsedContent["PickInLocation"]:
		shipping_address_doc = billing_address_doc
	else:
		# if "In store pickup" is selected, create a new address for the shipping address if it does not exist
		existing_shipping_address = check_existing_address(shipping_address_detail, "Shipping")
		if existing_shipping_address:
			# If an existing shipping address is found, fetch its document.
			shipping_address_doc = frappe.get_doc("Address", existing_shipping_address)
		else:
			# If no shipping address is found, create a new one.
			shipping_address_doc = create_address(shipping_address_detail, customer, "Shipping")

	# Return the billing address document, shipping address document, and th
	return billing_address_doc, shipping_address_doc, customer

# extract order details from the parsed content
def get_order_detail(parsedContent, province, country, company, shipping_item, is_billing_cp_verified):
	return {
		"order_id": parsedContent['orderNumber'],
		"order_date": parsedContent['orderDate'], 
		"items": parsedContent['items'],
		"discounts": parsedContent['Discounts'],
		"total_value": parsedContent['totalValueAmount'], 
		"total_shipping_amount": parsedContent['totalShippingAmount'] if "totalShippingAmount" in parsedContent else 0.0,
		"total_discount_amount": parsedContent['TotalDiscount'] if "TotalDiscount" in parsedContent else 0.0,
		"source": parsedContent['publisher_site'],
		"taxes_and_charges": get_taxes_and_charges(province, country, company),
		"currency": parsedContent['grandTotalAmount']['Currency']["isoCode"],
		"company": company,
		"shipping_item": shipping_item,
		"signifyd": parsedContent['SignifyD'],
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
def get_shipping_item(shipping_quote, total):
	shipping_item = ""
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


def get_or_create_customer(lead_source, billing_address_detail, shipping_address_detail, billing_address_doc=None, shipping_address_doc=None):
	# If a billing address document exists, attempt to find an existing customer based on it.
	if billing_address_doc:
		existing_customer = check_existing_customer(billing_address_doc, billing_address_detail)
		
		# If an existing customer is found, return it immediately.
		if existing_customer:
			return existing_customer

	# Create a new Customer record in the system using billing address details.
	customer = frappe.get_doc({
		"doctype": "Customer",
		"first_name": billing_address_detail['first_name'],  # Customer's first name
		"last_name": billing_address_detail['last_name'],    # Customer's last name
		"customer_name": billing_address_detail['first_name'] + " " + billing_address_detail['last_name'],  # Full name
		"territory": billing_address_detail['country'],  # Country as the territory
		# Default price list is fetched from the Lead Source; if not available, fallback to "RET - Camo".
		"default_price_list": frappe.db.get_value("Lead Source", lead_source, "custom_neb_price_list") or "RET - Camo",
		"billing_currency": billing_address_detail['currency'],  # Customer's billing currency
		"posa_referral_code": billing_address_detail['account_id'],  # Referral code from billing details
		"pincode": billing_address_detail['postal_code'],  # Customer's postal code
	})

	# Insert the new Customer record into the database.
	customer.insert()

	# If a billing address document exists, create a Dynamic Link to associate it with the new Customer.
	if billing_address_doc:
		dynamic_link = frappe.new_doc("Dynamic Link")
		dynamic_link.update({
			"link_doctype": "Customer",  # The doctype to link (Customer in this case)
			"link_name": customer.name  # The name of the newly created customer
		})

	# Create a Contact record for the Customer using their billing details.
	contact = create_contact(billing_address_detail, customer.name)

	# Commit the changes to the database to save the new Customer and Contact records.
	frappe.db.commit()

	# Return the name of the newly created Customer.
	return customer.name

def check_existing_customer(billing_address_doc, billing_address_detail):
	if billing_address_doc.links:
		for link in billing_address_doc.links:
			if link.get("link_doctype") == "Customer":
				first_name, last_name = frappe.db.get_value("Customer", link.get("link_name"), ["first_name", "last_name"])
				if first_name == billing_address_detail["first_name"] and last_name == billing_address_detail["last_name"]:
					return link.get("link_name")

	return None

def create_order(order_detail, customer, shipping_address_doc, billing_address_doc):
	items = process_items(order_detail['items'], shipping_item=order_detail['shipping_item'], order_detail=order_detail)
	new_order = frappe.get_doc({
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
		"billing_address_name": billing_address_doc.name,
		"ifw_signifyd_sid": order_detail['signifyd']['Sid'],
		"ifw_signifyd_caseid": order_detail['signifyd']['CaseId'],
		"ifw_signifyd_casestatus": order_detail['signifyd']['CaseStatus'],
		"ifw_signifyd_approved": order_detail['signifyd']['IsApproved'],
		"ifw_signifyd_score": order_detail['signifyd']['Score'],
		"ifw_signifyd_guaranteedisposition": order_detail['signifyd']['GuarenteedDisposition'],
		"ifw_signifyd_fulfilled": order_detail['signifyd']['Fullfilled'],
		"ifw_store_pickup": order_detail["ifw_store_pickup"],
		"discount_amount": order_detail["total_discount_amount"],
		"ignore_pricing_rule": 1,  # Ignore pricing rules for this order
		"is_rush": is_rush(items)
	})

	# set the missing values for the order and submit it if the gateway is not "interacetransfer"
	new_order.set_missing_values()
	new_order.save()
	new_order.submit()

	frappe.db.commit()
	return new_order

def is_rush(items):
    for item in items:
        print(item.get("item_code"))
        if item.get("item_code") == "99992":
            return True
    return False

def create_address(address_detail, customer, address_type):
	address = frappe.get_doc({
		"doctype": "Address",
		"ifw_first_name": address_detail["first_name"],
		"ifw_last_name": address_detail["last_name"],
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
	return frappe.db.exists("Address", 
						{
							"ifw_first_name": address_detail["first_name"],
							"ifw_last_name": address_detail["last_name"],
							"phone": address_detail["phone"], 
							"address_type": address_type,
							"pincode": address_detail["postal_code"],
							"state": address_detail["state"],
						}
					)

def create_contact(contact_detail, customer):
	check_existing = frappe.db.exists("Contact", 
										{
											"email_id": contact_detail["email"], 
											"phone": contact_detail["phone"],
											"first_name": contact_detail["first_name"],
											"last_name": contact_detail["last_name"]
										}
									)

	if check_existing:
		return check_existing

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

	# link the contact to the customer
	dynamic_link = frappe.new_doc("Dynamic Link")
	dynamic_link.update({
		"link_doctype": "Customer",
		"link_name": customer
	})

	contact.links.append(dynamic_link)

	# save the contact
	contact.insert()
	frappe.db.commit()

	return contact.name

# This method processes a list of items and creates corresponding "Sales Order Item" documents.
# For each item in the input list, it generates a new Sales Order Item with the provided details (SKU, quantity, unit price, and warehouse).
# If a shipping item is provided, it also creates a Sales Order Item for the shipping charges.
# Finally, it returns a list of all the created Sales Order Item documents.
def create_payment(payment_detail, order, company):
	try:
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
		new_payment.reference_no = order.neb_usaepay_transaction_key
		new_payment.reference_date = remove_tz_from_date(payment_detail['transactions']["createdOn"])
		new_payment.save()

		can_be_submitted = True
		if transaction_detail.get("paymentGatewayAlias") == "paypalexpress" and transaction_detail.get("orderTransactionState") == 1:
			can_be_submitted = False
      
		if can_be_submitted:
			new_payment.submit()
		frappe.db.commit()

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

def get_taxes_and_charges(province, country, company=None):
	company_code = frappe.db.get_value("Company", company, "abbr")
	if province == "Texas":
		return f"Texas - {company_code}"
	elif province == "Alberta":
		return "Alberta - ICL"
	elif province == "British Columbia":
		return "British Columbia - ICL"
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
	elif province == "Quebec":
		return "Quebec GST and QST - ICL"
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
		
def process_items(items, shipping_item, order_detail):
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

	if shipping_item:
		new_shipping_item = frappe.get_doc({
			"doctype": "Sales Order Item",
			"item_code": shipping_item['item_code'],
			"qty": shipping_item['qty'],
			"price_list_rate": shipping_item['rate'],
			"warehouse": warehouse
		})  
		items_list.append(new_shipping_item)

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
		post_to_rocket_chat([], f"Unable to update SignifyD details: {str(e)}", rmq=True)
  
def create_rmq_log(parsedContent):
	try:
		publisher_site = parsedContent.get("publisher_site", "Unknown")
		rmq_log = frappe.get_doc({
			"doctype": "RabbitMQ Orders Log",
			"payload": as_unicode(parsedContent),
			"lead_source": publisher_site
		})
		rmq_log.insert()
		return rmq_log.name
		frappe.db.commit()
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
