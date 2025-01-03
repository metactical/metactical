from zeep import Client, Settings, xsd
from requests.auth import HTTPBasicAuth
import frappe
from requests import Session
from zeep.transports import Transport
import re
import logging
from frappe.utils import get_files_path
import base64
from metactical.custom_scripts.utils.metactical_utils import get_state_code
import ast
from six import string_types

# logging.basicConfig(level=logging.DEBUG)
# logging.getLogger('zeep').setLevel(logging.DEBUG)

class Purolator:
	def __init__(self):
		self.settings = self.get_settings()

	def get_settings(self):
		"""Fetches the enabled Purolator settings from the Frappe doctype 'Purolator Settings'"""
		settings = frappe.get_all('Purolator Settings', filters={'enabled': 1}, limit=1)
		if not settings:
			frappe.throw("No enabled Purolator Settings found")
		settings = frappe.get_doc('Purolator Settings', settings[0].name)
		return frappe._dict({
				'api_key': settings.api_key,
				'api_password': settings.get_password('api_password'),
				'is_sandbox': settings.is_sandbox,
				'billing_account': settings.billing_account
			})
	
	def breakdown_phone_number(self, phone_number):
		pattern = re.compile(r'^\+?1?[-.\s]?(\d{3})[-.\s]?(\d{3})[-.\s]?(\d{4})$')
		
		match = pattern.match(phone_number)
		
		if match:
			country_code = '1'
			area_code = match.group(1)
			phone = match.group(2) + match.group(3)
			return country_code, area_code, phone
		else:
			raise frappe.throw("Invalid phone number format for Canada/US")


	def create_pwss_soap_client(self, wsdl_url, reference):
		"""Creates a SOAP Client with the appropriate authentication and header information"""
		session = Session()
		session.auth = HTTPBasicAuth(self.settings['api_key'], self.settings['api_password'])
		transport = Transport(session=session)
		settings = Settings(strict=False, xml_huge_tree=True)
		client = Client(wsdl=wsdl_url, transport=transport, settings=settings)

		#Define the SOAP Envelope Headers
		header = xsd.Element(
			'{http://purolator.com/pws/datatypes/v2}RequestContext',
			xsd.ComplexType([
				xsd.Element('{http://purolator.com/pws/datatypes/v2}Version', xsd.String()),
				xsd.Element('{http://purolator.com/pws/datatypes/v2}Language', xsd.String()),
				xsd.Element('{http://purolator.com/pws/datatypes/v2}GroupID', xsd.String()),
				xsd.Element('{http://purolator.com/pws/datatypes/v2}RequestReference', xsd.String())
			])
		)
		header_value = header(Version='2.0', Language='en', GroupID='xxx', RequestReference=reference)
		client.set_default_soapheaders([header_value])

		return client

	def get_rate(self, docname):
		data = []
		options = {}

		if self.settings.is_sandbox:
			wsdl_url = 'https://devwebservices.purolator.com/EWS/V2/Estimating/EstimatingService.asmx?wsdl'
		else:
			wsdl_url = 'https://webservices.purolator.com/EWS/V2/Estimating/EstimatingService.asmx?wsdl'
		
		client = self.create_pwss_soap_client(wsdl_url, docname)

		shipment = frappe.get_doc("Shipment", docname)
		sender_postal_code = frappe.db.get_value("Address", shipment.pickup_address_name, "pincode").replace(" ", "")
		customer_address = frappe.get_doc("Address", shipment.delivery_address_name)
		state = customer_address.state
		if len(state) > 2:
			state = get_state_code(state)

		receiver_address = {
			"City": customer_address.city,
			"Province": state.upper(),
			"Country": frappe.db.get_value("Country", customer_address.country, "code").upper(),
			"PostalCode": customer_address.pincode.replace(" ", "")
		}

		for row in shipment.shipment_parcel:
			items = []
			request = {
				'SenderPostalCode': sender_postal_code,
				'ReceiverAddress': receiver_address,
				'PackageType': 'CustomerPackaging',
				'TotalWeight': {
					'Value': row.weight,
					'WeightUnit': 'kg'
				}
			}

			response = client.service.GetQuickEstimate(**request)
			response = response.body
			print(response)

			# Check if the response is valid and contains ShipmentEstimates
			if response and hasattr(response, 'ShipmentEstimates') and hasattr(response.ShipmentEstimates, 'ShipmentEstimate'):
				for estimate in response.ShipmentEstimates.ShipmentEstimate:
					options[estimate.ServiceID] = estimate.ServiceID
					items.append({
						'carrier_service': estimate.ServiceID,
						'service_name': estimate.ServiceID,
						'base': estimate.BasePrice,
						'shipment_amount': estimate.TotalPrice,
						'guaranteed_delivery': "Unknown",
						'expected_transit_time': estimate.EstimatedTransitDays,
						'expected_delivery_date': estimate.ExpectedDeliveryDate,
					})

			if items:
				data.append({
					'name': row.name,
					'idx': row.idx,
					'count': row.count,
					'items': items,
				})
			else:
				print("ShipmentEstimate property is not set in the response.")
				print(response)
		return {"data": data, 'options': [{'key': k, 'val': v} for k, v in options.items()]}
	
	def create_shipment(self, docname, selected_service):

		if isinstance(selected_service, string_types) and selected_service.startswith('{'):
			selected_service = ast.literal_eval(selected_service)

		if self.settings.is_sandbox:
			wsdl_url = 'https://devwebservices.purolator.com/EWS/V2/Shipping/ShippingService.asmx?wsdl'
		else:
			wsdl_url = 'https://webservices.purolator.com/EWS/V2/Shipping/ShippingService.asmx?wsdl'
		
		client = self.create_pwss_soap_client(wsdl_url, docname)

		shipment = frappe.get_doc("Shipment", docname)

		sender_address = frappe.get_doc("Address", shipment.pickup_address_name)
		receiver_address = frappe.get_doc("Address", shipment.delivery_address_name)

		sender_street_number = sender_address.address_line1.split(" ")[0]
		sender_street_name = " ".join(sender_address.address_line1.split(" ")[1:])
		sender_country_code, sender_area_code, sender_phone = self.breakdown_phone_number(sender_address.phone)

		receiver_street_number = receiver_address.address_line1.split(" ")[0]
		receiver_street_name = " ".join(receiver_address.address_line1.split(" ")[1:])

		sender_state = sender_address.state
		if len(sender_state) > 2:
			sender_state = get_state_code(sender_state)

		receiver_state = receiver_address.state
		if len(receiver_state) > 2:
			receiver_state = get_state_code(receiver_state)

		request = {
			'Shipment': {
				'SenderInformation': {
					'Address': {
						'Name': shipment.pickup_company,
						'Company': shipment.pickup_company,
						'StreetNumber': sender_street_number,
						'StreetName': sender_street_name,
						'StreetType': "Street",
						'City': sender_address.city,
						'Province': sender_state,
						'Country': frappe.db.get_value("Country", sender_address.country, "code"),
						'PostalCode': sender_address.pincode.replace(" ", ""),
						'PhoneNumber': {
							'CountryCode': sender_country_code,
							'AreaCode': sender_area_code,
							'Phone': sender_phone
						}
					}
				},
				'ReceiverInformation': {
					'Address': {
						'Name': frappe.db.get_value('Customer', shipment.delivery_customer, 'customer_name'),
						'Company': receiver_address.company,
						'StreetNumber': receiver_street_number,
						'StreetName': receiver_street_name,
						'StreetType': "Street",
						'City': receiver_address.city,
						'Province': receiver_state,
						'Country': frappe.db.get_value("Country", receiver_address.country, "code"),
						'PostalCode': receiver_address.pincode.replace(" ", "")
					}
				},
				'PackageInformation': {
					'TotalWeight': {
						'Value': sum(row.weight for row in shipment.shipment_parcel),
						'WeightUnit': 'kg'
					},
					'TotalPieces': len(shipment.shipment_parcel),
					'ServiceID': selected_service[shipment.shipment_parcel[0].name],
					'Description': shipment.shipment_type,
					'PiecesInformation': {
						'Piece': [{
							'Weight': {
								'Value': piece.weight,
								'WeightUnit': 'kg'
							},
							'Length': {
								'Value': piece.length,
								'DimensionUnit': 'cm'
							},
							'Width': {
								'Value': piece.width,
								'DimensionUnit': 'cm'
							},
							'Height': {
								'Value': piece.height,
								'DimensionUnit': 'cm'
							}
						} for piece in shipment.shipment_parcel]
					}
				},
				'PaymentInformation': {
					'PaymentType': "Sender",
					'RegisteredAccountNumber': self.settings['billing_account'],
					'BillingAccountNumber': self.settings['billing_account']
				},
				'PickupInformation': {
					'PickupType': 'PreScheduled'
				},
				'TrackingReferenceInformation': {
					'Reference1': docname
				}
			},
			'PrinterType': 'Thermal'
		}
		print(request)

		validate_shipment = client.service.ValidateShipment(Shipment=request["Shipment"])
		if not validate_shipment.body.ValidShipment:
			frappe.throw(str(validate_shipment.body))
		else:
			create_shipment = client.service.CreateShipment(Shipment=request["Shipment"])
			if create_shipment.body.ResponseInformation.Errors is None:
				shipment_pin = create_shipment.body.ShipmentPIN.Value
				print(create_shipment)
				response = self.get_documents(docname, shipment_pin)
				shipment.ais_shipment_status = "Shipped"
				shipment.save()
				return response
			else:
				frappe.throw(str(create_shipment.body))

	def get_documents(self, docname, pin):
		if self.settings.is_sandbox:
			wsdl_url = 'https://devwebservices.purolator.com/PWS/V1/ShippingDocuments/ShippingDocumentsService.asmx?wsdl'
		else:
			wsdl_url = 'https://webservices.purolator.com/PWS/V1/ShippingDocuments/ShippingDocumentsService.asmx?wsdl'

		client = self.create_pwss_soap_client(wsdl_url, docname)

		header = xsd.Element(
				'{http://purolator.com/pws/datatypes/v1}RequestContext',
				xsd.ComplexType([
					xsd.Element('{http://purolator.com/pws/datatypes/v1}Version', xsd.String()),
					xsd.Element('{http://purolator.com/pws/datatypes/v1}Language', xsd.String()),
					xsd.Element('{http://purolator.com/pws/datatypes/v1}GroupID', xsd.String()),
					xsd.Element('{http://purolator.com/pws/datatypes/v1}RequestReference', xsd.String())
				])
			)
		header_value = header(Version='1.3', Language='en', GroupID='xxx', RequestReference=docname)

		request_data = {
			'DocumentCriterium': {
				'DocumentCriteria': {
					'PIN': {
						'Value': pin
					}, 
					'DocumentTypes': {
						'DocumentType': "DomesticBillOfLading"
					}
				}
			},
			'OutputType': 'PDF',
			'Synchronous': True
		}

		response = client.service.GetDocuments(_soapheaders=[header_value], **request_data)
		documents = response.body.Documents.Document
		files = []
		for document in documents:
			for detail in document.DocumentDetails.DocumentDetail:
				files.append(self.write_file(docname, detail.Data))
		return files
	
	def write_file(self, docname, data, file_name=None, field_name=None):
		if not file_name:
			file_name = f'{docname}.pdf'
		file_path = get_files_path(f"{file_name}", is_private=True)
		binary_data = base64.b64decode(data)

		with open(file_path, 'wb') as f:
			f.write(binary_data)
			# f.close()

		file_doc = frappe.new_doc('File')
		file_url = file_path.replace(frappe.get_site_path(), '')
		file_doc.update({
			'file_name': f"{file_name}",
			'file_url': file_url,
			'is_private': 1,
			'folder': 'Home/Attachments',
			'attached_to_doctype': 'Shipment',
			'attached_to_name': docname,
			'attached_to_field': field_name,
			'file_size': data,
		})
		file_doc.insert(ignore_permissions=True)
		return file_doc.file_url

# def test():
# 	# cp = CanadaPost()
# 	# ret = cp.get_rate(name="SHIPMENT-00124")
# 	# print(ret)
# 	purolator = Purolator()
# 	ret = purolator.create_shipment("SHIPMENT-00127", '{"da2pusruq6": "PurolatorGround"}')
# 	#ret = purolator.get_documents('SHIPMENT-00124', '329015010179')
# 	print(ret)