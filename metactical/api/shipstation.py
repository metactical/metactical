import frappe
from lxml import etree
from werkzeug.wrappers import Response
import requests
from requests.auth import HTTPBasicAuth

def get_orders(start_date, end_date):
	orders = frappe.get_all('Sales Order', fields=['name', 'transaction_date', 'status', 'modified', 'currency', 'grand_total', 'customer', 
									'customer_address', 'shipping_address_name'], 
									filters={"delivery_status": ("in", ("Not Delivered", "Partly Delivered")), "billing_status": "Fully Billed", 
									"modified": ("between", (start_date, end_date))})
	return orders

@frappe.whitelist(allow_guest=True)
def test():
	response = requests.get('https://ssapi.shipstation.com/stores',
				auth=('42edf2c7a56e4289b0cb184dc040eb4b', 'f124798829b144f7a14752e67a1a7ec4'))	
	print(response)
	print(response.json())


@frappe.whitelist(allow_guest=True)
def connect():
	response = requests.get('https://ssapi.shipstation.com/orders',
				auth=('42edf2c7a56e4289b0cb184dc040eb4b', 'f124798829b144f7a14752e67a1a7ec4'))	
	print(response)
	print(response.json())
	
@frappe.whitelist()
def create_shipstation_orders(order_no=None):
	settings = get_settings()
	if order_no is not None:
		data = order_json(order_no, settings)
		response = requests.post('https://ssapi.shipstation.com/orders/createorder',
					auth=(settings.api_key, settings.get_password('api_secret')),
					json=data)
		#print(response.status_code)
		#print(response.json())
		
	
	

def order_json(order_no, settings):
	order = frappe.get_doc('Delivery Note', order_no)
	
	#For shipping and taxes charges
	shipping_settings = settings.shipping_charges_specified
	shipping_item = None
	shipping_charges = 0
	taxes = 0
	if shipping_settings == 'In Item Table':
		shipping_item = settings.shipping_item
		taxes = order.total_taxes_and_charges
	elif shipping_settings == 'In Charges Table':
		shipping_item = settings.shipping_charge
		for charge in order.taxes:
			if charge.account_head == shipping_item:
				shipping_charges = charge.tax_amount_after_discount_amount
			else:
				taxes = taxes + float(charge.tax_amount_after_discount_amount)
	
	#For address
	if order.customer_address and order.customer_address is not None:
		customer_address = frappe.get_doc('Address', order.customer_address)
		country = frappe.get_value('Country', customer_address.country, "code")
		
	items = []
	for item in order.items:
		#Check if it is a shipping item
		if shipping_settings == 'In Item Table' and item.item_code == shipping_item:
			shipping_charges = item.amount
		else:
			row = {}
			row.update({
				"lineItemKey": item.name,
				"sku": item.item_code,
				"name": item.item_name,
				"imageUrl": None,
				"weight": None,
				"quantity": int(item.qty),
				"unitPrice": float(item.rate),
				"taxAmount": None,
				"shippingAmount": None,
				"warehouseLocation": None,
				"options": None,
				"productId": None,
				"fulfillmentSku": None,
				"adjustment": False,
				"upc": None
			})
			items.append(row)
	data = {}
	data.update({
		"orderNumber": order.name,
		"orderKey": order.name,
		"orderDate": str(order.posting_date),
		"paymentDate": None,
		"shipByDate": "",
		"orderStatus": "awaiting_shipment",
		"customerUsername": order.customer,
		"customerEmail": customer_address.email_id,
		"billTo": {
			"name": order.customer,
			"company": '',
			"street1": customer_address.address_line1,
			"street2": customer_address.address_line1,
			"street3": '',
			"city": customer_address.city,
			"state": customer_address.state,
			"postalCode": '',
			"country": country,
			"phone": customer_address.phone,
			"residential": None
		},
		"shipTo": {
			"name": order.customer,
			"company": "",
			"street1": customer_address.address_line1,
			"street2": customer_address.address_line1,
			"street3": '',
			"city": customer_address.city,
			"state": customer_address.state,
			"postalCode": '',
			"country": country,
			"phone": customer_address.phone,
			"residential": None
		},
		"items": items,
		"amountPaid": order.grand_total,
		"taxAmount": float(taxes),
		"shippingAmount": float(shipping_charges),
		"customerNotes": None,
		"internalNotes": None,
		"gift": False,
		"giftMessage": None,
		"paymentMethod": None,
		"requestedShippingService": None,
		"carrierCode": None,
		"serviceCode": None,
		"packageCode": None,
		"confirmation": "none",
		"shipDate": None,
		"weight": None,
		"dimensions": None
	})
	return data

def get_settings():
	settings = frappe.get_doc('Shipstation Settings')
	return settings
