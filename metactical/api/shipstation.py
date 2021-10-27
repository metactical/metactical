import frappe
from lxml import etree
from werkzeug.wrappers import Response
import requests
from requests import Request
from requests.auth import HTTPBasicAuth
import json
from urllib.parse import urlparse, parse_qs

def get_orders(start_date, end_date):
	orders = frappe.get_all('Sales Order', fields=['name', 'transaction_date', 'status', 'modified', 'currency', 'grand_total', 'customer', 
									'customer_address', 'shipping_address_name'], 
									filters={"delivery_status": ("in", ("Not Delivered", "Partly Delivered")), "billing_status": "Fully Billed", 
									"modified": ("between", (start_date, end_date))})
	return orders

@frappe.whitelist(allow_guest=True)
def test():
	'''response = requests.get('https://ssapi.shipstation.com/stores',
				auth=('', ''))
	data = {"resource_url": "https://ssapi6.shipstation.com/shipments?batchId=190671332&includeShipmentItems=False", "resource_type": "SHIP_NOTIFY" }
	response = requests.post('http://deverp.metactical.com/api/method/metactical.api.shipstation.orders_shipped_webhook?settingid=8f3a7e2cac',
				json=data)				
	print(response)
	print(response.json())'''
	frappe.request = Request('Post', "http://deverp.metactical.com/api/method/metactical.api.shipstation.orders_shipped_webhook?settingid")
	return frappe.request


@frappe.whitelist(allow_guest=True)
def connect():
	response = requests.get('https://ssapi.shipstation.com/orders',
				auth=('', ''))	
	print(response)
	print(response.json())
	
@frappe.whitelist()
def create_shipstation_orders(order_no=None, is_cancelled=False):
	#order_no = 'MAT-DN-2021-00039'
	if order_no is not None:
		order = frappe.get_doc('Delivery Note', order_no)
		if order.get('is_return') == 1:
			return
		source = None
		if order.get('source') is not None:
			source = order.get('source')
		shipstation_settings = get_settings(source)
		
		#Determine already set orderIDs (from previous requests)
		orderIds = []
		for row in order.ais_shipstation_order_ids:
			orderIds.append(row.settings_id)
		
		for settings in shipstation_settings:
			data = order_json(order, is_cancelled, settings)
			response = requests.post('https://ssapi.shipstation.com/orders/createorder',
						auth=(settings.api_key, settings.get_password('api_secret')),
						json=data)
			if response.status_code == 200:
				#To prevent adding orderIds multiple times
				if settings.name not in orderIds: 
					sorder = response.json()
					#frappe.db.set_value('Delivery Note', order_no, "ais_shipstation_orderid", sorder.get('orderId'))
					order_table = frappe.new_doc('Shipstation Order ID', order, 'ais_shipstation_order_ids')
					order_table.update({
									'settings_id': settings.name,
									'shipstation_order_id': sorder.get('orderId')
								})
					order_table.save()
		
	
	

def order_json(order, is_cancelled, settings):
	#order = frappe.get_doc('Delivery Note', order)
	
	#Order no is either pick list name or delivery note name
	order_no = None
	if order.pick_list and order.pick_list is not None:
		order_no = order.pick_list
	else:
		order_no = order.name
		
	orderStatus = "awaiting_shipment"
	if is_cancelled:
		orderStatus = "cancelled"
	
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
	'''customer_address = {
		'address_line1': None,
		'address_line2': None,
		'city': None,
		'state': None,
		'pincode': None,
		'phone': None,
		'email_id': None
	}'''
	customer_address = {}
	customer_country = None
	if order.customer_address and order.customer_address is not None:
		customer_address = frappe.get_doc('Address', order.customer_address)
		customer_country = frappe.get_value('Country', customer_address.country, "code")
		customer_country = customer_country.upper()
	
	#Get shipping address, if none, use customer address
	shipping_address = {}
	shipping_country = None
	if order.shipping_address_name and order.shipping_address_name is not None:
		shipping_address = frappe.get_doc('Address', order.shipping_address_name)
		shipping_country = frappe.get_value('Country', shipping_address.country, "code")
		shipping_country = shipping_country.upper()
	elif order.customer_address and order.customer_address is not None:
		shipping_address = customer_address
		shipping_country = frappe.get_value('Country', shipping_address.country, "code")
		shipping_country = shipping_country.upper()
		
	#For stores
	storeId = None
	if order.source and order.source is not None:
		for store in settings.store_mapping:
			if order.source == store.source:
				storeId = store.store_id
		
	items = get_items(order, shipping_settings, shipping_item)
	
	data = {}
	data.update({
		"orderNumber": order_no,
		"orderKey": order_no,
		"orderDate": str(order.posting_date),
		"paymentDate": None,
		"shipByDate": "",
		"orderStatus": orderStatus,
		"customerUsername": order.customer,
		"customerEmail": customer_address.get('email_id'),
		"billTo": {
			"name": order.customer,
			"company": '',
			"street1": customer_address.get('address_line1'),
			"street2": customer_address.get('address_line2'),
			"street3": '',
			"city": customer_address.get('city'),
			"state": customer_address.get('state'),
			"postalCode": customer_address.get('pincode'),
			"country": customer_country,
			"phone": customer_address.get('phone'),
			"residential": None
		},
		"shipTo": {
			"name": order.customer,
			"company": "",
			"street1": shipping_address.get('address_line1'),
			"street2": shipping_address.get('address_line2'),
			"street3": '',
			"city": shipping_address.get('city'),
			"state": shipping_address.get('state'),
			"postalCode": shipping_address.get('pincode'),
			"country": shipping_country,
			"phone": shipping_address.get('phone'),
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
		"dimensions": None,
		"advancedOptions": {
			"storeId": storeId
		}
	})
	return data

def get_settings(source=None, settingid=None):
	settings = []
	if source is not None:
		parents = frappe.db.sql('''SELECT parent FROM `tabShipstation Store Map` WHERE source = %(source)s''', {"source": source}, as_dict=1)
		if len(parents) > 0:
			for parent in parents:
				ret = frappe.get_doc('Shipstation Settings', parent.parent)
				if ret.disabled != 1:
					settings.append(ret)
			
	if settingid is not None:
		ret = frappe.get_doc('Shipstation Settings', settingid)
		settings.append(ret)
		
	if len(settings) == 0 and settingid is None:
		default = frappe.db.get_value('Shipstation Settings', {"is_default": 1, "disabled": 0})
		ret = frappe.get_doc('Shipstation Settings', default)
		settings.append(ret)
		
	return settings
	
def get_items(doc, shipping_settings, shipping_item):
	items = []
	#Get bundled items
	bundled_items = []
	for item in doc.packed_items:
		bundled_items.append(item.parent_item)
		row = {}
		row.update({
			"lineItemKey": item.name,
			"sku": item.item_code,
			"name": item.item_name,
			"imageUrl": None,
			"weight": None,
			"quantity": int(item.qty),
			"unitPrice": 0,
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
	
	for item in doc.items:
		#Check if it is a shipping item
		if shipping_settings == 'In Item Table' and item.item_code == shipping_item:
			shipping_charges = item.amount
		elif item.item_code not in bundled_items: #Make sure it's not a bundled item
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
	return items
	
@frappe.whitelist(allow_guest=True)
def orders_shipped_webhook():
	url = urlparse(frappe.request.url)
	params = parse_qs(url.query)
	settingid = params.get("settingid")
	data = json.loads(frappe.request.data)
	resource_url = data.get("resource_url")
	resource_type = data.get("resource_type")
	if settingid is not None:
		frappe.set_user('Administrator')
		#Log the request
		new_req = frappe.get_doc({
			"doctype": "Shipstation API Requests",
			"start_date": resource_url,
			"end_date": resource_type,
			"settingid": settingid[0]
		})
		if resource_type == 'SHIP_NOTIFY':
			settings = get_settings(settingid=settingid[0])
			if len(settings) > 0:
				response = requests.get(resource_url,
							auth=(settings[0].api_key, settings[0].get_password('api_secret')))
				new_req.update({
					"result": json.dumps(response.json())
				})
				shipments = response.json()
				weight_display = ''
				size = ''
				for shipment in shipments.get('shipments'):
					weight = shipment.get('weight')
					if weight_display != '':
						weight_display =+ ' | '
					weight_display += str(weight.get('value')) + ' ' + weight.get('units')
					dimensions = shipment.get('dimensions')
					if size != '':
						size += ' | '
					size += str(dimensions.get('length')) + 'l x ' + str(dimensions.get('width')) + 'w x ' + str(dimensions.get('height')) + 'h'
					
					#For carrier mapping
					transporter = ''
					for row in settings[0].transporter_mapping:
						if row.carrier_code == shipment.get('carrierCode'):
							transporter = row.transporter
					pick_list = shipment.get('orderNumber')
					shipDate = shipment.get('shipDate')
					trackingNumber = shipment.get('trackingNumber')
					shipmentCost = shipment.get('shipmentCost')
					
					#Update delivery note
					existing_delivery = frappe.db.get_value('Delivery Note', {'pick_list': pick_list})
					if existing_delivery:
						delivery_note = frappe.get_doc('Delivery Note', existing_delivery)
						delivery_note.update({
							'lr_date': shipDate,
							'lr_no': trackingNumber,
							'transporter': transporter,
							'ais_shipment_cost': shipmentCost,
							'ais_package_weight': weight_display,
							'ais_package_size': size,
							'ais_updated_by_shipstation': 1
						})
						delivery_note.submit()
						
						#Delete order from other shipstation accounts
						for row in delivery_note.get('ais_shipstation_order_ids'):
							if row.settings_id != settingid[0]:
								shipstation_settings = frappe.get_doc('Shipstation Settings', row.settings_id)
								if shipstation_settings.disabled != 1:
									response = requests.delete('https://ssapi.shipstation.com/orders/' + row.shipstation_order_id,
										auth=(shipstation_settings.api_key, shipstation_settings.get_password('api_secret')))
						
		new_req.insert(ignore_if_duplicate=True)
	
	
@frappe.whitelist(allow_guest=True)
def shipstation_xml():
	root = etree.Element("Orders")
	out = etree.tostring(root, pretty_print=True)
	response = Response()
	response.mimetype = "text/xml"
	response.charset = "utf-8"
	response.data = out
	return response
	
@frappe.whitelist()
def get_shipment():
	response = requests.get('https://ssapi6.shipstation.com/shipments?batchId=187980859&includeShipmentItems=False',
				auth=('249b9201157349939742f12101a8cc80', '1d7b6409ba6e41e1aeae73b97384613d'))
	print(response.status_code)
	print(response.json())
	shipments = response.json()
	for shipment in shipments.get('shipments'):
		existing_delivery = frappe.db.get_value('Delivery Note', {'po_no': shipment.get('orderNumber'), 'docstatus': 0})
		if existing_delivery:
			delivery_note = frappe.get_doc('Delivery Note', existing_delivery)
			delivery_note.update({
				'lr_date': shipment.get('shipDate'),
				'lr_no': shipment.get('trackingNumber')
			})
			delivery_note.save()
			
def delete_order(order_no):
	#order_no = 'MAT-DN-2021-00030'
	order = frappe.get_doc('Delivery Note', order_no)
	for row in order.get('ais_shipstation_order_ids'):
		settings = frappe.get_doc('Shipstation Settings', row.settings_id)
		if settings.disabled == 0:
			response = requests.delete('https://ssapi.shipstation.com/orders/' + row.shipstation_order_id,
				auth=(settings.api_key, settings.get_password('api_secret')))
