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
	
	
@frappe.whitelist()
def sync_shipping_status():
	settings = get_settings()
	response = requests.get('https://ssapi.shipstation.com/shipments?shipDateStart=2022-08-07',
				auth=(settings[0].api_key, settings[0].get_password('api_secret')))
	shipments = response.json()
	frappe.set_user(settings[0].shipstation_user)
	for shipment in shipments.get('shipments'):
		exists = frappe.db.exists('Delivery Note',  {'pick_list': shipment.get('orderKey'), 'docstatus': 0})
		if exists:
			weight_display = ''
			size = ''
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
			delivery_note = frappe.get_doc('Delivery Note', existing_delivery)
			delivery_note.update({
				'lr_date': shipDate,
				'lr_no': trackingNumber,
				'transporter': transporter,
				'ais_shipment_cost': shipmentCost,
				'ais_package_weight': weight_display,
				'ais_package_size': size,
				'ais_updated_by_shipstation': 1,
				'ignore_pricing_rule': 1
			})
			try:
				delivery_note.submit()
			except Exception as e:
				frappe.log_error(frappe.get_traceback())
				
			#Delete order from other shipstation accounts
			'''for row in delivery_note.get('ais_shipstation_order_ids'):
				if row.settings_id != settingid[0]:
					shipstation_settings = frappe.get_doc('Shipstation Settings', row.settings_id)
					if shipstation_settings.disabled != 1:
						response = requests.delete('https://ssapi.shipstation.com/orders/' + row.shipstation_order_id,
							auth=(shipstation_settings.api_key, shipstation_settings.get_password('api_secret')))'''	
	
@frappe.whitelist()
def create_shipstation_orders(order_no=None, is_cancelled=False):
	if order_no is not None:
		order = frappe.get_doc('Delivery Note', order_no)
		if order.get('is_return') == 1:
			return
		source = None
		if order.get('source') is not None:
			source = order.get('source')
		shipstation_settings = get_settings(source)
		if len(shipstation_settings) == 0:
			return
		
		#Determine already set orderIDs (from previous requests)
		orderIds = []
		for row in order.ais_shipstation_order_ids:
			orderIds.append(row.settings_id)
		
		for settings in shipstation_settings:
			data = order_json(order, is_cancelled, settings)
			orders_url = 'https://ssapi.shipstation.com/orders/createorder'
			response = requests.post(orders_url,
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
			else:
				#Add it to Shipstation API requests for troubleshooting
				new_req = frappe.new_doc('Shipstation API Requests')
				new_req.update({
					"resource_url": orders_url,
					"resource_type": 'CREATE_ORDER',
					"result": response.text,
					"reference_type": "Delivery Note",
					"reference_name": order_no
				})
				new_req.insert(ignore_permissions=True)
		
	
	

def order_json(order, is_cancelled, settings):
	#order = frappe.get_doc('Delivery Note', order_no)
	
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
				"imageUrl": item.get('image'),
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
	
	# Get customer and shipping name from the addresses
	customer_name = "{} {}".format(customer_address.get("ifw_first_name"), customer_address.get("ifw_last_name"))
	shipping_name = "{} {}".format(shipping_address.get("ifw_first_name"), shipping_address.get("ifw_last_name"))
	
	if customer_name.strip() == "":
		customer_name = order.customer
		
	if shipping_name.strip() == "":
		shipping_name = order.customer
	
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
			"name": customer_name,
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
			"name": shipping_name,
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
		parents = frappe.db.sql('''SELECT ssm.parent FROM `tabShipstation Store Map` AS ssm 
					LEFT JOIN 
						`tabShipstation Settings` AS ss ON ssm.parent = ss.name
					WHERE 
						ssm.source = %(source)s AND ss.disabled = 0''', {"source": source}, as_dict=1)
		if len(parents) > 0:
			for parent in parents:
				ret = frappe.get_doc('Shipstation Settings', parent.parent)
				settings.append(ret)
			
	if settingid is not None:
		ret = frappe.get_doc('Shipstation Settings', settingid)
		settings.append(ret)
		
	if len(settings) == 0 and settingid is None:
		default = frappe.db.get_value('Shipstation Settings', {"is_default": 1, "disabled": 0})
		if default:
			ret = frappe.get_doc('Shipstation Settings', default)
			settings.append(ret)
		
	return settings
	
@frappe.whitelist(allow_guest=True)
def orders_shipped_webhook():
	url = urlparse(frappe.request.url)
	params = parse_qs(url.query)
	settingid = params.get("settingid")
	data = json.loads(frappe.request.data)
	resource_url = data.get("resource_url")
	resource_type = data.get("resource_type")
	if settingid is not None:
		settings = get_settings(settingid=settingid[0])
		if len(settings) > 0:
			frappe.set_user(settings[0].shipstation_user)
			#Log the request
			new_req = frappe.get_doc({
				"doctype": "Shipstation API Requests",
				"resource_url": resource_url,
				"resource_type": resource_type,
				"settingid": settingid[0]
			})
			if resource_type == 'SHIP_NOTIFY':
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
							'ais_updated_by_shipstation': 1,
							'ignore_pricing_rule': 1
						})

						try:
							delivery_note.submit()
						except Exception as e:
							frappe.log_error(frappe.get_traceback())
						
						#Add reference to Shipstation API Requests
						new_req.update({
							'reference_type': 'Delivery Note',
							'reference_name': existing_delivery
						})
						
						#Delete order from other shipstation accounts
						for row in delivery_note.get('ais_shipstation_order_ids'):
							if row.settings_id != settingid[0]:
								shipstation_settings = frappe.get_doc('Shipstation Settings', row.settings_id)
								if shipstation_settings.disabled != 1:
									response = requests.delete('https://ssapi.shipstation.com/orders/' + row.shipstation_order_id,
										auth=(shipstation_settings.api_key, shipstation_settings.get_password('api_secret')))
									
						# Update shipment doctype
						shipment_details = frappe._dict({
							'receipt_number': trackingNumber,
							'receipt_date': shipDate,
							'transporter': transporter,
							'weight_uom': weight.get('units'),
							'size_uom': dimensions.get('units'),
							'length': dimensions.get('length'),
							'width': dimensions.get('width'),
							'height': dimensions.get('height'),
							'weight': weight.get('value'),

						})
						update_shipment(existing_delivery, shipment_details)
							
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
			
def delete_order(order_no):
	#order_no = 'MAT-DN-2021-00030'
	order = frappe.get_doc('Delivery Note', order_no)
	for row in order.get('ais_shipstation_order_ids'):
		settings = frappe.get_doc('Shipstation Settings', row.settings_id)
		if settings.disabled == 0:
			response = requests.delete('https://ssapi.shipstation.com/orders/' + row.shipstation_order_id,
				auth=(settings.api_key, settings.get_password('api_secret')))
			
def update_shipment(delivey_note, shipment_details):
	shipment_exists = frappe.db.exists('Shipment Delivery Note', {'delivery_note': delivey_note, 'docstatus': 0})
	if shipment_exists:
		shipment = frappe.db.get_value('Shipment Delivery Note', shipment_exists, 'parent')
		shipment = frappe.get_doc('Shipment', shipment)
		shipment.update({
			'ais_shipstation_transporter': shipment_details.get('transporter'),
			'ais_shipstation_receipt_no': shipment_details.get('receipt_number'),
			'ais_shipstation_receipt_date': shipment_details.get('receipt_date'),
			'ais_shipment_status': 'Shipped'
		})

		# Convert weight from ounces to kgs and and size from inches to cms
		if shipment_details.get("weight_uom") == "ounces":
			shipment_details["weight"] = float(shipment_details.get("weight", 0)) / 35.274

		if shipment_details.get("size_uom") == "inches":
			shipment_details['length'] = shipment_details.get('length', 0) * 2.54
			shipment_details['width'] = shipment_details.get('width', 0) * 2.54
			shipment_details['height'] = shipment_details.get("height", 0) * 2.54

		shipment.shipment_parcel = []
		shipment.append('shipment_parcel', {
			'length': shipment_details.get('length'),
			'width': shipment_details.get('width'),
			'height': shipment_details.get('height'),
			'weight': shipment_details.get('weight'),
			'count': 1
		})
		try:
			shipment.submit()
		except Exception as e:
			frappe.log_error(frappe.get_traceback())
