from zeep import Client, Settings, xsd
from requests.auth import HTTPBasicAuth
import frappe
from requests import Session
from zeep.transports import Transport
from metactical.utils.shipping.canada_post import CanadaPost

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


	def create_pwss_soap_client(self, wsdl_url):
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
		header_value = header(Version='2.0', Language='en', GroupID='xxx', RequestReference='Rating Example')
		client.set_default_soapheaders([header_value])

		return client

	def get_rate(self, docname):
		data = []
		options = {}

		if self.settings.is_sandbox:
			wsdl_url = 'https://devwebservices.purolator.com/EWS/V2/Estimating/EstimatingService.asmx?wsdl'
		else:
			wsdl_url = 'https://webservices.purolator.com/EWS/V2/Estimating/EstimatingService.asmx?wsdl'
		
		client = self.create_pwss_soap_client(wsdl_url)

		shipment = frappe.get_doc("Shipment", docname)
		sender_postal_code = frappe.db.get_value("Address", shipment.pickup_address_name, "pincode").replace(" ", "")
		customer_address = frappe.get_doc("Address", shipment.delivery_address_name)
		receiver_address = {
			"City": customer_address.city,
			"Province": customer_address.state.upper(),
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
					#print(f"{estimate.ServiceID} is available for ${estimate.TotalPrice}")

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
		if self.settings.is_sandbox:
			wsdl_url = 'https://devwebservices.purolator.com/EWS/V2/Shipping/ShippingService.asmx?wsdl'
		else:
			wsdl_url = 'https://webservices.purolator.com/EWS/V2/Shipping/ShippingService.asmx?wsdl'
		
		client = self.create_pwss_soap_client(wsdl_url)

		shipment = frappe.get_doc("Shipment", docname)

		sender_address = frappe.get_doc("Address", shipment.pickup_address_name)
		receiver_address = frappe.get_doc("Address", shipment.delivery_address_name)

		sender_street_number = sender_address.address_line1.split(" ")[0]
		sender_street_name = " ".join(sender_address.address_line1.split(" ")[1:])

		receiver_street_number = receiver_address.address_line1.split(" ")[0]
		receiver_street_name = " ".join(receiver_address.address_line1.split(" ")[1:])

		request = {
			'Shipment': {
				'ShipmentDate': '2024-12-30',
				'SenderInformation': {
					'Address': {
						'Name': shipment.pickup_company,
						'Company': shipment.pickup_company,
						'StreetNumber': sender_street_number,
						'StreetName': sender_street_name,
						'StreetType': "Street",
						'City': sender_address.city,
						'Province': sender_address.state,
						'Country': frappe.db.get_value("Country", sender_address.country, "code"),
						'PostalCode': sender_address.pincode.replace(" ", "")
					}
				},
				'ReceiverInformation': {
					'Address': {
						'Name': shipment.delivery_customer,
						'Company': receiver_address.company,
						'StreetNumber': receiver_street_number,
						'StreetName': receiver_street_name,
						'StreetType': "Street",
						'City': receiver_address.city,
						'Province': receiver_address.state,
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
					'ServiceID': selected_service,
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
					'SenderAccountNumber': self.settings['billing_account'],
					'BillingAccountNumber': self.settings['billing_account']
				},
				'PickupInformation': {
					'PickupType': 'DropOff'
				},
				'TrackingReferenceInformation': {
					'Reference1': docname
				}
			},
			'PrinterType': 'Thermal'
		}
		#print(request)
		response = client.service.ValidateShipment(request)
		response = client.service.CreateShipment(request)
		return response


def test():
	# cp = CanadaPost()
	# ret = cp.get_rate(name="SHIPMENT-00124")
	# print(ret)
	purolator = Purolator()
	ret = purolator.create_shipment("SHIPMENT-00124", "PurolatorExpressEvening")
	print(ret)