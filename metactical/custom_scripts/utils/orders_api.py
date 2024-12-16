import frappe
from metactical.custom_scripts.utils.metactical_utils import remove_tz_from_date
from metactical.custom_scripts.payment_entry.payment_entry import get_payment_entry

def receive_rmq_data(message):
	try:
		# from metactical.custom_scripts.utils.data3 import parsedContent
		parsedContent = message
		taxes = parsedContent['taxes']["tax"] if "tax" in parsedContent['taxes'] else []
		province = parsedContent['shippingRegion']['name']
		country = parsedContent['shippingCountry']['name']
		company = frappe.db.get_single_value("Global Defaults", "default_company")
		shipping_quote = parsedContent["account"]["carts"][0]["selectedShippingQuote"]
		shipping_item = get_shipping_item(shipping_quote)

		billing_address_detail = {
			"first_name": parsedContent['billingFirstName'],
			"last_name": parsedContent['billingLastName'],
			"email": parsedContent['billingEmail'],
			"company": parsedContent['billingOrganization'],
			"phone": parsedContent['billingPhoneNumber'],
			"line1": parsedContent['billingLine1'],
			"line2": parsedContent['billingLine2'],
			"city": parsedContent['billingCity'],
			"region_code": parsedContent['billingRegionCode'],
			"postal_code": parsedContent['billingPostalCode'],
			"state": parsedContent['billingRegion']['name'],
			"country": parsedContent['billingCountry']['name'],
			"currency": parsedContent['grandTotalAmount']['Currency']["isoCode"],
		}

		shipping_address_detail = {
			"first_name": parsedContent['shippingFirstName'],
			"last_name": parsedContent['shippingLastName'],
			"email": parsedContent['shippingEmail'],
			"company": parsedContent['shippingOrganization'],
			"phone": parsedContent['shippingPhoneNumber'],
			"line1": parsedContent['shippingLine1'],
			"line2": parsedContent['shippingLine2'],
			"city": parsedContent['shippingCity'],
			"region_code": parsedContent['shippingRegionCode'],
			"postal_code": parsedContent['shippingPostalCode'],
			"state": parsedContent['shippingRegion']['name'],
			"country": parsedContent['shippingCountry']['name'],
			"currency": parsedContent['grandTotalAmount']['Currency']["isoCode"]
		}

		order_detail = {
			"order_id": parsedContent['orderNumber'],
			"order_date": parsedContent['orderDate'], 
			"items": parsedContent['items'],
			"taxes": parsedContent['taxes']["tax"] if "tax" in parsedContent['taxes'] else [],
			"discounts": parsedContent['Discounts'],
			"total_value": parsedContent['totalValueAmount'], 
			"total_shipping_amount": parsedContent['totalShippingAmount'],
			"total_discount_amount": parsedContent['TotalDiscountAmount']["Amount"],
			"source": parsedContent['publisher_site'],
			"taxes_and_charges": get_taxes_and_charges(taxes, province, country),
			"currency": parsedContent['grandTotalAmount']['Currency']["isoCode"],
			"company": company,
			"shipping_item": shipping_item,
		}
		
		payment_detail = {
			"transactions": parsedContent['transactions'],
		}

		customer = create_customer(billing_address_detail, lead_source=parsedContent['publisher_site'])
		order = create_order(order_detail, customer, billing_address_detail, shipping_address_detail)

		if parsedContent["PaymentGateway"] != "interacetransfer":
			payment = create_payment(payment_detail, order)

	except Exception as e:
		frappe.log_error(title='RabbitMQ Error', message=frappe.get_traceback())


def get_shipping_item(shipping_quote):
	shipping_item = shipping_quote['name']
	if shipping_item == "Standard Shipping":
		shipping_item = "Shipping"

	shipping_item_code = frappe.db.get_value("Item", {"item_name": shipping_item}, "item_code")
	if not shipping_item_code:
		return None

	return {
		"item_code": shipping_item_code,
		"qty": 1,
		"rate": shipping_quote['amount'],
	}

def create_customer(address, lead_source):
	new_customer = frappe.get_doc({
		"doctype": "Customer",
		"first_name": address['first_name'],
		"last_name": address['last_name'],
		"customer_name": address['first_name'] + " " + address['last_name'],
		"territory": address['state'],
		"default_price_list": frappe.db.get_value("Lead Source", lead_source, "custom_neb_price_list") or "RET - Camo",
		"billing_currency": address['currency'],
	})

	new_customer.insert()
	frappe.db.commit()

	return new_customer

def create_order(order_detail, customer, billing_address_detail, shipping_address_detail):
	billing_address = create_address(billing_address_detail, customer, "Billing")
	if (billing_address_detail["email"] == shipping_address_detail["email"] and 
		billing_address_detail["phone"] == shipping_address_detail["phone"]):

		shipping_address = billing_address
	else:
		shipping_address = create_address(shipping_address_detail, customer, "Shipping")
	
	new_order = frappe.get_doc({
		"doctype": "Sales Order",
		"customer": customer.name,
		"po_no": order_detail["order_id"],
		"items": process_items(order_detail['items'], shipping_item=order_detail['shipping_item']),
		"source": order_detail['source'],
		"taxes_and_charges": order_detail['taxes_and_charges'],
		"delivery_date": calculate_delivery_date(order_detail['order_date']),
		"discounts": order_detail['discounts'],
		"total_value": order_detail['total_value'],
		"total_shipping_amount": order_detail['total_shipping_amount'],
		"total_discount_amount": order_detail['total_discount_amount'],
		"currency": billing_address_detail['currency'],
		"transaction_date": remove_tz_from_date(order_detail['order_date']),
		"company": order_detail['company'],
		"billing_address_name": billing_address,
		"shipping_address_name": shipping_address
	})

	new_order.set_missing_values()
	new_order.submit()

	frappe.db.commit()
	return new_order

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
		"country": address_detail["country"]
	})

	dynamic_link = frappe.new_doc("Dynamic Link")
	dynamic_link.update({
		"link_doctype": "Customer",
		"link_name": customer
	})

	address.links.append(dynamic_link)

	address.insert()
	frappe.db.commit()

	return address.name

def process_items(items, shipping_item):
	items_list = []
	for item in items:
		new_item = frappe.get_doc({
			"doctype": "Sales Order Item",
			"item_code": item['sku'],
			"qty": item['quantity'],
			"rate": item['unitPrice'],
			"warehouse": "W01-WHS-Active Stock - ICL"
		})

		items_list.append(new_item)

	if shipping_item:
		new_shipping_item = frappe.get_doc({
			"doctype": "Sales Order Item",
			"item_code": shipping_item['item_code'],
			"qty": shipping_item['qty'],
			"rate": shipping_item['rate'],
			"warehouse": "W01-WHS-Active Stock - ICL"
		})

		items_list.append(new_shipping_item)

	return items_list

def create_payment(payment_detail, order):
	new_payment = get_payment_entry(order.doctype, order.name)
	new_payment.reference_no = "test"
	new_payment.reference_date = order.transaction_date
	new_payment.mode_of_payment = "Visa"
	new_payment.submit()
	frappe.db.commit()

	return new_payment

def calculate_delivery_date(order_date):
	day = frappe.utils.getdate(order_date).strftime("%A")
	if day == "Friday":
		return frappe.utils.add_to_date(order_date, days=3)
	elif day == "Saturday":
		return frappe.utils.add_to_date(order_date, days=2)

	return frappe.utils.add_to_date(order_date, days=1)

def get_taxes_and_charges(taxes, province, country):
	if country == "United States":
		return "Export - ICL"
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
	elif province == "Yukon":
		return "Yukon - ICL"
	else:
		return "Alberta - ICL"
		