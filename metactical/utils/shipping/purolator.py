from zeep import Client, Settings, xsd
from requests.auth import HTTPBasicAuth
import frappe
from requests import Session, Request
from zeep.transports import Transport
import re
import logging
from frappe.utils import get_files_path
import base64
from metactical.custom_scripts.utils.metactical_utils import get_state_code
import ast
from six import string_types
from frappe import _
import json
import requests
import re
import fitz
import os

class PostTransport(Transport):
	def load(self, url, data=None):
		request = Request('GET', url, params=data)
		prepared_request = self.session.prepare_request(request)
		response = self.session.send(prepared_request, timeout=self.load_timeout)
		response.raise_for_status()
		return response.content

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
				'billing_account': settings.billing_account,
				'purolator_supplier': settings.purolator_supplier
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
		session = requests.Session()
		session.auth = HTTPBasicAuth(self.settings['api_key'], self.settings['api_password'])
		transport = Transport(session=session)
		settings = Settings(strict=False, xml_huge_tree=True)

		current_file_path = os.path.abspath(__file__)
		wsdl_url = f"{os.path.dirname(current_file_path)}/{wsdl_url}"
		client = Client(wsdl=wsdl_url, transport=transport, settings=settings)

		# Define the SOAP Envelope Headers
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
			wsdl_url = "wsdl/develop/EstimatingService.wsdl"
		else:
			wsdl_url = "wsdl/production/EstimatingService.wsdl"
		
		client = self.create_pwss_soap_client(wsdl_url, docname)

		shipment = frappe.get_doc("Shipment", docname)
		sender_postal_code = frappe.db.get_value("Address", shipment.pickup_address_name, "pincode").replace(" ", "")
		customer_address = frappe.get_doc("Address", shipment.delivery_address_name)
		state = customer_address.state
		if len(state) > 2:
			state = get_state_code(state)

			if not state:
				frappe.throw("Error: Incorrect customer's state. Please fix and try again")

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

			# Check if the response is valid and contains ShipmentEstimates
			if response and hasattr(response, 'ShipmentEstimates') and hasattr(response.ShipmentEstimates, 'ShipmentEstimate') \
				and len(response.ShipmentEstimates.ShipmentEstimate) > 0:
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
			elif response and hasattr(response, 'ResponseInformation') and hasattr(response.ResponseInformation, 'Errors') \
				and len(response.ResponseInformation.Errors) > 0:
				error = self.render_error(response.ResponseInformation.Errors)
				frappe.throw(error)

			if items:
				data.append({
					'name': row.name,
					'idx': row.idx,
					'count': row.count,
					'items': items,
				})

		# Because with Purilator you can only select a single service even with multiple pieces,
		# combine the two rates into a single one to remove confusion
		return {"data": data, 'options': [{'key': k, 'val': v} for k, v in options.items()], "supports_multiple": False}
	
	def create_shipment(self, docname, selected_service):

		if isinstance(selected_service, string_types) and selected_service.startswith('{'):
			selected_service = ast.literal_eval(selected_service)

		if self.settings.is_sandbox:
			wsdl_url = 'wsdl/develop/ShippingService.wsdl'
		else:
			wsdl_url = 'wsdl/production/ShippingService.wsdl'
		
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
				'ShipmentDate': shipment.pickup_date,
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
					},
					'DangerousGoodsDeclarationDocumentIndicator': True if shipment.custom_dangerous_goods else False,
					'OptionsInformation': {
						'Options': {
							'OptionIDValuePair':
							[
								{
									'ID': 'DangerousGoods',
									'Value': True if shipment.custom_dangerous_goods else False
								},
								{
									'ID': 'DangerousGoodsClass',
									'Value': shipment.custom_dangerous_goods_class
								},
								{
									'ID': 'DangerousGoodsMode',
									'Value': shipment.custom_dangerous_goods_mode
								}
							]
						}
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

		if receiver_address.country != "Canada":
			request['Shipment']['InternationalInformation'] = {
				"DocumentsOnlyIndicator": True
			}
		print(request)

		validate_shipment = client.service.ValidateShipment(Shipment=request["Shipment"])
		if not validate_shipment.body.ValidShipment:
			errors = self.render_error(validate_shipment.body.ResponseInformation.Errors)
			frappe.throw(errors)
		else:
			create_shipment = client.service.CreateShipment(Shipment=request["Shipment"])
			if create_shipment.body.ResponseInformation.Errors is None:
				shipment.shipments = []
				piece_row = 0
				labels = []
				shipment_pin = None

				if create_shipment.body.ShipmentPIN:
					shipment_pin = create_shipment.body.ShipmentPIN

				for row in create_shipment.body.PiecePINs.PIN:
					piece_pin = row.Value
					label = self.get_documents(docname, piece_pin)[0]
					labels.append(label)
					shipment.append("shipments", {
						"service_provider": "Purolator",
						"shipment_id": piece_pin,
						"carrier_service": selected_service[shipment.shipment_parcel[0].name],
						"row_id": shipment.shipment_parcel[piece_row].name,
						"carrier_status": "created",
						"service_name": selected_service[shipment.shipment_parcel[0].name],
						"label": label
					})
					piece_row += 1

					if not shipment_pin:
						shipment_pin = piece_pin

				shipment.ais_shipment_status = "Shipped"
				shipment.save()
				frappe.db.set_value("Shipment", shipment.name, "service_provider", "Purolator")
				self.update_delivery_note(shipment, shipment_pin)
				return labels
			else:
				errors = self.render_error(create_shipment.body.ResponseInformation.Errors)
				frappe.throw(errors)

	def update_delivery_notes(self, shipment, tracking_no):
		delivery_notes = []
		for row in shipment.shipment_delivery_note:
			if row.delivery_note not in delivery_notes:
				delivery_notes.append(row.delivery_note)

		purolator_supplier = self.settings.purolator_supplier
		if purolator_supplier:
			for delivery_note in delivery_notes:
				frappe.db.set_value("Delivery Note", delivery_note, "transporter", purolator_supplier)
				frappe.db.set_value("Delivery Note", delivery_note, "lr_no", tracking_no)
				frappe.db.set_value("Delivery Note", delivery_note, "lr_date", frappe.utils.nowdate())

	def get_documents(self, docname, pin):
		if self.settings.is_sandbox:
			wsdl_url = 'wsdl/develop/ShippingDocumentsService.wsdl'
		else:
			wsdl_url = 'wsdl/production/ShippingDocumentsService.wsdl'

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
				binary_data = base64.b64decode(detail.Data)
				files.append(self.write_file('Shipment', docname, binary_data, file_name=f"{pin}.pdf"))
		return files
	
	def write_file(self, doctype, docname, data, file_name=None, field_name=None):
		if not file_name:
			file_name = f'{docname}.pdf'
		file_path = get_files_path(f"{file_name}", is_private=True)
		
		with open(file_path, 'wb') as f:
			f.write(data)
			# f.close()

		file_doc = frappe.new_doc('File')
		file_url = file_path.replace(frappe.get_site_path(), '')
		file_doc.update({
			'file_name': f"{file_name}",
			'file_url': file_url,
			'is_private': 1,
			'folder': 'Home/Attachments',
			'attached_to_doctype': doctype,
			'attached_to_name': docname,
			'attached_to_field': field_name,
			'file_size': data,
		})
		file_doc.insert(ignore_permissions=True)
		return file_doc.file_url
	
	def void_shipment(self, docname, shipments=[]):
		if isinstance(shipments, string_types) and shipments.startswith('['):
			shipments = ast.literal_eval(shipments)

		if len(shipments) == 0:
			frappe.throw(_("Please select min one shipment"))

		doc = frappe.get_doc('Shipment', docname)
		to_be_removed = []
		for shipment in doc.get('shipments', {'name': ('in', shipments or [])}):
			if self.settings.is_sandbox:
				wsdl_url = 'wsdl/develop/ShippingService.wsdl'
			else:
				wsdl_url = 'wsdl/production/ShippingService.wsdl'
			
			client = self.create_pwss_soap_client(wsdl_url, docname)

			request_data = {
				'PIN': {
					'Value': shipment.shipment_id
				}
			}
			response = client.service.VoidShipment(**request_data)
			if response.body.ShipmentVoided:
				to_be_removed.append(shipment)
			else:
				errors = self.render_error(response.body.ResponseInformation.Errors)
				frappe.throw(errors)

		for shipment in to_be_removed:
			doc.remove(shipment)

		if len(doc.shipments) == 0:
			doc.ais_shipment_status = "Not Shipped"
		
		doc.save()
		return doc.as_dict()
	
	def consolidate_shipments(self, manifest_doc):
		manifest_date = frappe.db.get_value("Manifest", manifest_doc, 'pickup_date')
		if self.settings.is_sandbox:
			wsdl_url = "wsdl/develop/ShippingService.wsdl"
		else:
			wsdl_url = "wsdl/production/ShippingService.wsdl"

		client = self.create_pwss_soap_client(wsdl_url, manifest_doc)
		response = client.service.Consolidate()
		if response.body.Consolidate:
			return self.get_manifest_document(manifest_doc, manifest_date)
		else:
			return response

	def get_manifest_document(self, manifest_docname, manifest_date):
		po_number = None
		shipments = []
		if self.settings.is_sandbox:
			wsdl_url = 'wsdl/develop/ShippingDocumentsService.wsdl'
		else:
			wsdl_url = 'wsdl/production/ShippingDocumentsService.wsdl'

		client = self.create_pwss_soap_client(wsdl_url, manifest_docname)

		header = xsd.Element(
				'{http://purolator.com/pws/datatypes/v1}RequestContext',
				xsd.ComplexType([
					xsd.Element('{http://purolator.com/pws/datatypes/v1}Version', xsd.String()),
					xsd.Element('{http://purolator.com/pws/datatypes/v1}Language', xsd.String()),
					xsd.Element('{http://purolator.com/pws/datatypes/v1}GroupID', xsd.String()),
					xsd.Element('{http://purolator.com/pws/datatypes/v1}RequestReference', xsd.String())
				])
			)
		header_value = header(Version='1.3', Language='en', GroupID='xxx', RequestReference=manifest_docname)
		request = {
			'ShipmentManifestDocumentCriterium': {
				'ShipmentManifestDocumentCriteria': {
					'ManifestDate': manifest_date
				}
			}
		}
		response = client.service.GetShipmentManifestDocument(_soapheaders=[header_value], **request)
		if response.body.ManifestBatches:
			manifests = response.body.ManifestBatches.ManifestBatch
			for manifest in manifests:
				manifest_docs = manifest.ManifestBatchDetails.ManifestBatchDetail
				for manifest_doc in manifest_docs:
					url = manifest_doc.URL
					response = requests.get(url)
					if response.status_code == 200:
						content = response.content
						print({"content": content})
						self.write_file("Manifest", manifest_docname, content, f"manifest_{manifest_docname}.pdf")
						po_number = self.extract_manifest_no(content)
						
						doc = frappe.get_doc("Manifest", manifest_docname)
						for item in doc.items:
							shipments.append(item.shipment_id)
					else:
						frappe.log_error(message=f"Failed to download content from {url}", title="Purolator Manifet Error")
		return shipments, po_number

	def extract_manifest_no(self, content):
		document = fitz.open(stream=content, filetype="pdf")
		text = ''
		for page_num in range(len(document)):
			page = document.load_page(page_num)
			text += page.get_text()

		match = re.search(r'Manifest Number:\s*(\d+)', text)
		if match:
			return match.group(1)
		return None
	
	def update_manifest(self, docname, po_number):
		if po_number is None:
			po_number = docname

		doc = frappe.get_doc("Manifest", docname)
		doc.update({
			""
		})
		
	
	def render_error(self, errors):
		ret = """
				<table class="table table-bordered">
					<tr>
						<th>Code</th>
						<th> Description </th>
					</tr>"""

		for error in errors.Error:
			ret += f"""<tr>
							<th>{error.Code}</th>
							<td>{error.Description}</td>
						</tr>"""
		ret += """</table>"""
		return ret
	
def test():
	# cp = CanadaPost()
	# ret = cp.get_rate(name="SHIPMENT-00124")
	# print(ret)
	purolator = Purolator()
	ret = purolator.create_shipment("SHIPMENT-00195", '{"d4u1o7u699": "PurolatorExpressU.S."}')
	#ret = purolator.get_documents('SHIPMENT-00124', '329015010179')
	#ret = purolator.void_shipment('SHIPMENT-00128', '["bcobed5l9v"]')
	#ret = purolator.get_rate('SHIPMENT-00142')
	#ret = purolator.consolidate_shipments('MF-10-17-2023-201952', '2025-01-23')
	print(ret)