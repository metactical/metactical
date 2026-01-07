import frappe
import requests
from frappe import _, get_desk_link, bold
import xmltodict
from requests.auth import _basic_auth_str
from frappe.utils import get_files_path
from six import string_types
import ast
from PyPDF2 import PdfFileMerger
from metactical.custom_scripts.utils.metactical_utils import get_state_code
from datetime import datetime
import re
import time


class CanadaPost():
	def __init__(self) -> None:
		self.settings = frappe.get_cached_doc('Canada Post', 'Canada Post')
		if any([not self.settings.get(field) for field in ("enabled", "api_key", "api_secret", "customer_number", "contract_number")]):
			frappe.throw(_("Please Complete Canada Post Settings {}").format(
				bold(get_desk_link(self.settings.doctype, self.settings.doctype))))
		self._init_session()

	def __exit__(self) -> None:
		self.sess.close()

	def _init_session(self):
		self.sess = requests.Session()
		self.set_default_headers()
		self.sess.verify = True

	def set_default_headers(self):
		self.sess.headers = {
			'Accept': 'application/vnd.cpc.shipment-v8+xml',
			'Content-Type': 'application/vnd.cpc.shipment-v8+xml; charset=utf-8',
			'Accept-language': 'en-CA',
			'Authorization': _basic_auth_str(self.settings.api_key, self.settings.get_password("api_secret"))
		}
		self.sess.verify = False

	def xml_to_json(self, data):
		return xmltodict.parse(data)

	def json_to_xml(self, data):
		return xmltodict.unparse(data, pretty=True)

	def get_context(self, name, context=None):
		doc = frappe.get_doc('Shipment', name)
		if not doc.shipment_parcel:
			frappe.throw(_("Should be min one Shiopment Parcel row"))
		if context:
			doc.update(context)
		doc.shipment_type = self.get_shipment_type(doc.shipment_type)
		delivery_address_doc = frappe.get_doc(
			'Address', doc.delivery_address_name).as_dict()
		
		if len(delivery_address_doc.state) > 2:
			delivery_address_doc.state = get_state_code(delivery_address_doc.state)

		if delivery_address_doc.pincode is None or delivery_address_doc.pincode == "":
			frappe.throw(f"Postal code needed in shipping address {delivery_address_doc.name}")
		else:
			delivery_address_doc.pincode = delivery_address_doc.pincode.upper()

		# Check if shipment is to the US and validate the non-delivery handling option
		if delivery_address_doc.country == "United States" or delivery_address_doc.country_code == "US":
			if not doc.custom_nondelivery_handling_option:
				frappe.throw(_(
					"For US shipments, the Non-Delivery Handling Option is required. "
					"Please set the 'Non-Delivery Handling Option' field in the shipment document."
				))
			
		pickup_address_doc = frappe.get_doc(
			'Address', doc.pickup_address_name).as_dict()
		
		if pickup_address_doc.state is None or pickup_address_doc.state == "":
			frappe.throw(f"State needed in billing address {pickup_address_doc.name}.")

		if pickup_address_doc.pincode is None or pickup_address_doc.pincode == "":
			frappe.throw(f"Postal code needed in billing address {pickup_address_doc.name}")
		else:
			pickup_address_doc.pincode = pickup_address_doc.pincode.upper()

		if len(pickup_address_doc.state) > 2:
			pickup_address_doc.state = get_state_code(pickup_address_doc.state)
		pickup_person_doc = frappe.get_doc(
			'User', doc.pickup_contact_person).as_dict()
		delivery_contact_doc = frappe.get_doc(
			'Contact', doc.delivery_contact_name).as_dict()
		customer_first_name, customer_last_name = frappe.db.get_value("Customer", doc.delivery_customer, ["first_name", "last_name"])
		delivery_contact_doc.first_name = customer_first_name
		delivery_contact_doc.last_name = customer_last_name
		delivery_note = frappe.get_doc(
			'Delivery Note', doc.shipment_delivery_note[-1].delivery_note).as_dict()
		return frappe._dict({
			"doc": doc.as_dict(),
			"settings": self.settings.as_dict(),
			"delivery_address_doc": delivery_address_doc,
			"pickup_address_doc": pickup_address_doc,
			"delivery_contact_doc": delivery_contact_doc,
			"pickup_contact_person_doc": pickup_person_doc,
			"delivery_note": delivery_note,
		})
		

	def get_shipment_type(self, s_type):
		return {
			"Document": "DOC",
			"Commercial Sample": "SAM",
			"Repair or Warranty": "REP",
			"Goods": "SOG",
			"Other": "OTH",
		}[s_type]

	def get_rate(self, name, context=None):
		res = []
		options = {}
		context = self.get_context(name, context)
		exists = self.existing_shipments(context.doc)
		for parcel in context.doc.shipment_parcel:
			if (parcel.count - exists.get(parcel.name, 0)) < 1:
				continue
			context.parcel = parcel
			context.parcel.weight = round(float(context.parcel.weight), 2)
			context.parcel.height = round(float(context.parcel.height), 2)
			context.parcel.length = round(float(context.parcel.length), 2)
			context.parcel.width = round(float(context.parcel.width), 2)

			body = frappe.render_template(
				"metactical/utils/shipping/templates/canada_post/request/get_rate.xml", context)
			response = self.get_response("/rs/ship/price", body, 
							{'Accept': 'application/vnd.cpc.ship.rate-v4+xml',
							'Content-Type': 'application/vnd.cpc.ship.rate-v4+xml; charset=utf-8'})
			items = []
			if response and response['price-quotes'] and response['price-quotes']['price-quote']:
				for pq in response['price-quotes']['price-quote']:
					options[pq['service-code']] = pq['service-name']
					items.append({
						'carrier_service': pq['service-code'],
						'service_name': pq['service-name'],
						'base': pq['price-details']['base'],
						'shipment_amount': pq['price-details']['due'],
						'guaranteed_delivery': pq['service-standard']['guaranteed-delivery'],
						'expected_transit_time': pq['service-standard']['expected-transit-time'],
						'expected_delivery_date': pq['service-standard']['expected-delivery-date'],
					})
			if items:
				res.append({
					'name': parcel.name,
					'idx': parcel.idx,
					'count': parcel.count,
					'items': items,
				})
		return {'data': res, 'options': [{'key': k, 'val': v} for k, v in options.items()]}

	def create_shipping(self, name, carrier_service, service_name, shipment_amount):
		if carrier_service is None:
			frappe.throw(_("Service Code Required. please select service"))

		if isinstance(carrier_service, string_types) and carrier_service.startswith('{'):
			carrier_service = ast.literal_eval(carrier_service)

		if isinstance(service_name, string_types) and service_name.startswith('{'):
			service_name = ast.literal_eval(service_name)

		files = []
		doc = frappe.get_doc('Shipment', name)
		context = self.get_context(name)
		exists = self.existing_shipments(context.doc)
		pickup_date = datetime.strftime(doc.pickup_date, "%Y%m%d")
		context.pickup_date = pickup_date
		context.group_id = f'{doc.warehouse.split("-")[0].replace(" ", "")}-{pickup_date}'
		context.options = []

		if doc.custom_ais_require_signature:
			context.options.append('SO')

		if doc.custom_ais_do_not_safe_drop and context.delivery_address_doc.country == "Canada":
			context.options.append('DNS')

		if context.delivery_address_doc.country == "United States" and doc.custom_nondelivery_handling_option:
			non_delivery_options = {
				"Return at Sender's Expense": "RASE",
				"Return to Sender": "RTS",
				"Abandon": "ABAN"
			}

			if non_delivery_options.get(doc.custom_nondelivery_handling_option):
				context.options.append(non_delivery_options.get(doc.custom_nondelivery_handling_option))

		for parcel in context.doc.shipment_parcel:
			context.parcel = parcel
			context.parcel.carrier_service = carrier_service.get(parcel.name)
			context.parcel.service_name = service_name.get(parcel.name)
			context.parcel.weight = round(float(context.parcel.weight), 2)
			context.parcel.height = round(float(context.parcel.height), 2)
			context.parcel.length = round(float(context.parcel.length), 2)
			context.parcel.width = round(float(context.parcel.width), 2)

			for c in range(parcel.idx - exists.get(parcel.name, 0)):
				body = frappe.render_template(
					"metactical/utils/shipping/templates/canada_post/request/create_shipment.xml", context)
				
				# Special character replacement for both lowercase and uppercase characters
				replacements = {
					"é": "e", "É": "E",
					"è": "e", "È": "E",
					"ê": "e", "Ê": "E",
					"ë": "e", "Ë": "E",
					"à": "a", "À": "A",
					"â": "a", "Â": "A",
					"ç": "c", "Ç": "C",
					"î": "i", "Î": "I",
					"ï": "i", "Ï": "I",
					"ô": "o", "Ô": "O",
					"ù": "u", "Ù": "U",
					"û": "u", "Û": "U",
					"ü": "u", "Ü": "U"
				}
				
				for char, replacement in replacements.items():
					body = body.replace(char, replacement)

				response = self.get_response(
					f"/rs/{self.settings.customer_number}/{self.settings.customer_number}/shipment", 
								body, 
								{'Accept': 'application/vnd.cpc.shipment-v8+xml',
								'Content-Type': 'application/vnd.cpc.shipment-v8+xml; charset=utf-8'})
				row = doc.append('shipments', {
					'shipment_id': response['shipment-info']['shipment-id'],
					'awb_number': response['shipment-info']['tracking-pin'],
					'service_provider': 'Canada Post',
					'service_name': context.parcel.service_name,
					'carrier_service': context.parcel.carrier_service,
					'tracking_status': '',
					'carrier_status': response['shipment-info']['shipment-status'],
					'row_id': parcel.name
				})
				for link in response['shipment-info']['links']['link']:
					rel = 'tracking' if link['@rel'] == "self" else link['@rel']
					row.set(
						f'{rel}_url', f"""<link rel="{link['@rel']}" href="{link['@href']}" media-type="{link['@media-type']}"></link>""")
					if link['@rel'] == "label":
						self.get_label(row, link, 'label', files)
					elif link['@rel'] == "price":
						self.set_price(row, link)
				row.db_insert()

		doc.ais_shipment_status = "Shipped"
		doc.save()
		frappe.db.set_value("Shipment", name, "service_provider", "Canada Post")
		frappe.db.set_value("Shipment", name, "shipment_amount", shipment_amount)
		self.update_delivery_note(doc, response['shipment-info']['tracking-pin'])
		# Merger PDFs.
		if files:
			files = [self.pdf_merge(files, doc).file_url]
		return files
	
	def update_delivery_note(self, doc, tracking_no):
		delivery_notes = []
		for row in doc.shipment_delivery_note:
			if row.delivery_note not in delivery_notes:
				delivery_notes.append(row.delivery_note)

		canada_post_supplier = frappe.db.get_single_value("Canada Post", "canada_post_supplier")
		if canada_post_supplier:
			for delivery_note in delivery_notes:
				frappe.db.set_value("Delivery Note", delivery_note, "transporter", canada_post_supplier)
				frappe.db.set_value("Delivery Note", delivery_note, "lr_no", tracking_no)
				frappe.db.set_value("Delivery Note", delivery_note, "lr_date", frappe.utils.nowdate())

	def set_price(self, row, link):
		res = self.get_response(link['@href'], None, {'Accept': link['@media-type'],
													  'Content-Type': link['@media-type']}, method='GET')
		if res:
			row.set('shipment_amount', res['shipment-price']['due-amount'])

	def pdf_merge(self, files, doc, prefix="before"):
		file_path = get_files_path(
			f"{prefix}_manifest_{doc.name}.pdf", is_private=True)
		wFile = PdfFileMerger()
		for file in files:
			wFile.append(frappe.get_site_path(file.lstrip('/')))
		wFile.write(file_path)
		wFile.close()
		file = self.create_file_doc(
			f"{prefix}_manifest_{doc.name}.pdf", file_path, doc)
		return file

	def existing_shipments(self, doc):
		shipments = frappe._dict()
		for d in doc.get('shipments', []):
			if not shipments.get(d.row_id):
				shipments[d.row_id] = 0
			shipments[d.row_id] = shipments[d.row_id]+1
		return shipments
		
	def create_manifest(self, manifest):
		context = frappe._dict()
		doc = frappe.get_doc("Manifest", manifest)
		shipment_ids = []
		po_number = None
		context.manifest_doc = doc
		context.pickup_address_doc = frappe.get_doc("Address", doc.pickup_address)
		context.pickup_contact_person_doc = frappe.get_doc("User", doc.pickup_contact_person)
		context.groups = self.get_shipments_groups(doc)
		if not context.groups or len(context.groups) == 0:
			frappe.throw("Error: There are no shipments that have not been transmitted.")

		context.warehouse_doc = frappe.get_doc('Warehouse', doc.warehouse)
		context.warehouse_doc.state = get_state_code(context.warehouse_doc.state)
		body = frappe.render_template(
			"metactical/utils/shipping/templates/canada_post/request/transmit_shipment.xml", context)
		
		response = self.get_response(
				f"/rs/{self.settings.customer_number}/{self.settings.customer_number}/manifest", body, 
				headers={'Accept': 'application/vnd.cpc.manifest-v8+xml', 
				'Content-Type': 'application/vnd.cpc.manifest-v8+xml; charset=utf-8'})
		
		if response:
			if isinstance(response['manifests']['link'], dict):
				links = [response['manifests']['link']]
			else:
				links = response['manifests']['link']
			for link in links:
				res = self.get_response(link['@href'], None, {'Accept': link['@media-type'],
															  'Content-Type': link['@media-type']}, method='GET')
				if res and res['manifest']['po-number']:
					po_number = res['manifest']['po-number']
					for mlink in res['manifest']['links']['link']:
						if mlink['@rel']=="artifact":
							manifest_file = self.get_response(
									mlink['@href'], None, {'Accept': mlink['@media-type'], 'Content-Type': mlink['@media-type']}, True, 'GET')
							if manifest_file.status_code == 200:
								file_name = f"manifest_{manifest}.pdf"
								file_path = get_files_path(f"{file_name}", is_private=True)
								with open(file_path, 'wb') as f:
									f.write(manifest_file.content)
								file_doc = frappe.new_doc('File')
								file_doc.update({
									'file_name': f"{file_name}",
									'file_url': file_path.replace(frappe.get_site_path(), ''),
									'is_private': 1,
									'folder': 'Home/Attachments',
									'attached_to_doctype': "Manifest",
									'attached_to_name': manifest
								})
								file_doc.insert(ignore_permissions=True)
						elif mlink["@rel"] == "manifestShipments":
							manifest_shipments = self.get_response(mlink["@href"], None, headers={'Accept': mlink["@media-type"]}, method="GET")
							if isinstance(manifest_shipments["shipments"]["link"], dict):
								shipment_links = [manifest_shipments["shipments"]["link"]]
							else:
								shipment_links = manifest_shipments["shipments"]["link"]
							for shipment in shipment_links:
								shipment_info = self.get_response(shipment["@href"], None, headers={'Accept': shipment["@media-type"]}, method="GET")
								shipment_ids.append(shipment_info["shipment-info"]['shipment-id'])
		return shipment_ids, po_number
							
	def get_shipments_groups(self, manifest_doc):
		groups = []
		pickup_dates = []
		for row in manifest_doc.items:
			pickup_date = frappe.db.get_value("Shipment", row.shipment, "pickup_date")
			if pickup_date not in pickup_dates:
				if isinstance(pickup_date, str):
					pickup_date = datetime.strptime(pickup_date, "%Y-%m-%d")
				groups.append(f'{manifest_doc.warehouse.split("-")[0].replace(" ", "")}-{datetime.strftime(pickup_date, "%Y%m%d")}')

		# Get available shipment groups and remove any that aren't available
		available_groups = self.get_available_groups()
		groups = [group for group in groups if group in available_groups]
		return groups

	def get_available_groups(self, return_links=False):
		available_groups = []
		response = self.get_response(
			f"/rs/{self.settings.customer_number}/{self.settings.customer_number}/group", None, 
			headers={'Accept': 'application/vnd.cpc.shipment-v8+xml'}, method="GET")
		
		# Ensure groups is a list
		groups = response["groups"]["group"]
		if isinstance(groups, dict):
			groups = [groups]
		
		for group in groups:
			if return_links:
				# Return both group-id and links structure
				available_groups.append({
					"group_id": group["group-id"],
					"links": group.get("links", {})
				})
			else:
				available_groups.append(group["group-id"])
		
		return available_groups

	def get_group_shipments(self, group_id=None, group_links=None):
		"""
		Get all shipments for a specific group ID
		Returns shipment details including references (ERP Shipment names)
		
		Args:
			group_id: The group ID to fetch shipments for (optional if group_links provided)
			group_links: Links dict from get_available_groups(return_links=True) (optional)
		"""
		shipments_data = []
		
		# If group_links provided, use them directly; otherwise fetch the group data
		if group_links and 'link' in group_links:
			links = group_links['link']
		else:
			# Fall back to fetching group data via API
			if not group_id:
				frappe.throw(_("Either group_id or group_links must be provided"))
			
			url = f"/rs/{self.settings.customer_number}/{self.settings.customer_number}/shipment?groupId={group_id}"
			headers = {'Accept': 'application/vnd.cpc.shipment-v8+xml'}
			
			try:
				response = self.get_response(url, None, headers=headers, method='GET')
			except Exception as e:
				# If group has no shipments or other error, return empty list
				frappe.log_error(
					title=f"Canada Post - Get Group Shipments Error for {group_id}",
					message=f"Error: {str(e)}\n{frappe.get_traceback()}"
				)
				return []
			
			if not response or 'shipments' not in response:
				return []
			
			if 'link' not in response['shipments']:
				return []
			
			links = response['shipments']['link']
		
		# Ensure links is a list
		if isinstance(links, dict):
			links = [links]
		
		for link in links:
			if link.get('@rel') == 'self':
				# This is the group link, skip it
				continue
			
			try:
				# Get individual shipment details
				shipment_response = self.get_response(
					link['@href'], 
					None, 
					headers={'Accept': link['@media-type']}, 
					method='GET'
				)
				
				if shipment_response and 'shipment-info' in shipment_response:
					shipment_info = shipment_response['shipment-info']
					
					# Extract the data we need
					shipment_data = {
						'shipment_id': shipment_info.get('shipment-id'),
						'tracking_pin': shipment_info.get('tracking-pin'),
						'shipment_status': shipment_info.get('shipment-status'),
						'group_id': group_id if group_id else shipment_info.get('group-id'),
						'references': {}
					}
						
					# Get customer references (this contains the ERP Shipment name)
					if 'customer-references' in shipment_info:
						refs = shipment_info['customer-references']
						if 'customer-ref-1' in refs:
							shipment_data['references']['ref_1'] = refs['customer-ref-1']
						if 'customer-ref-2' in refs:
							shipment_data['references']['ref_2'] = refs['customer-ref-2']
					
					# Get delivery address
					if 'delivery-spec' in shipment_info and 'destination' in shipment_info['delivery-spec']:
						dest = shipment_info['delivery-spec']['destination']
						shipment_data['delivery_customer'] = dest.get('name', '')
					
					# Get service information
					if 'delivery-spec' in shipment_info and 'service-code' in shipment_info['delivery-spec']:
						shipment_data['service_code'] = shipment_info['delivery-spec']['service-code']
					
					shipments_data.append(shipment_data)
			except Exception as e:
				# Log error but continue with other shipments
				frappe.log_error(
					title=f"Canada Post - Get Shipment Details Error",
					message=f"Error getting shipment from {link.get('@href', 'unknown')}: {str(e)}"
				)
				continue
		
		return shipments_data

	def get_manifests_by_date_range(self, from_date, to_date):
		"""
		Get all manifests within a date range from Canada Post API.
		
		Args:
			from_date: Start date in YYYY-MM-DD format
			to_date: End date in YYYY-MM-DD format
		
		Returns:
			list: List of manifest data with links
		"""
		# Convert dates to the format Canada Post expects (YYYYMMDD)
		if isinstance(from_date, str):
			from_date_obj = datetime.strptime(from_date, "%Y-%m-%d")
		else:
			from_date_obj = from_date
		
		if isinstance(to_date, str):
			to_date_obj = datetime.strptime(to_date, "%Y-%m-%d")
		else:
			to_date_obj = to_date
		
		# Validate date range (max 90 days)
		date_diff = (to_date_obj - from_date_obj).days
		if date_diff > 90:
			frappe.throw(_("Date range cannot exceed 90 days"))
		
		if date_diff < 0:
			frappe.throw(_("'To Date' must be after 'From Date'"))
		
		start_date_str = from_date_obj.strftime("%Y%m%d")
		end_date_str = to_date_obj.strftime("%Y%m%d")
		
		# Query Canada Post API for manifests
		url = f"/rs/{self.settings.customer_number}/{self.settings.customer_number}/manifest?start={start_date_str}&end={end_date_str}"
		headers = {'Accept': 'application/vnd.cpc.manifest-v8+xml'}
		
		try:
			response = self.get_response(url, None, headers=headers, method='GET')
		except Exception as e:
			frappe.log_error(
				title="Canada Post - Get Manifests Error",
				message=f"Error fetching manifests from {start_date_str} to {end_date_str}: {str(e)}\n{frappe.get_traceback()}"
			)
			return []
		
		if not response or 'manifests' not in response:
			return []
		
		# Ensure manifest links is a list
		manifest_links = response['manifests'].get('link', [])
		if isinstance(manifest_links, dict):
			manifest_links = [manifest_links]
		
		manifests_data = []
		
		for manifest_link in manifest_links:
			try:
				# Get detailed manifest info
				manifest_response = self.get_response(
					manifest_link['@href'], 
					None, 
					headers={'Accept': manifest_link['@media-type']}, 
					method='GET'
				)
				
				if manifest_response and 'manifest' in manifest_response:
					manifest_info = manifest_response['manifest']
					
					# Extract manifest data
					manifest_data = {
						'po_number': manifest_info.get('po-number'),
						'manifest_date': manifest_info.get('manifest-date'),
						'links': {}
					}
					
					# Store links for artifacts and shipments
					if 'links' in manifest_info and 'link' in manifest_info['links']:
						links = manifest_info['links']['link']
						if isinstance(links, dict):
							links = [links]
						
						for link in links:
							rel = link.get('@rel')
							if rel in ['artifact', 'manifestShipments']:
								manifest_data['links'][rel] = {
									'href': link['@href'],
									'media_type': link['@media-type']
								}
					
					manifests_data.append(manifest_data)
					
			except Exception as e:
				frappe.log_error(
					title="Canada Post - Get Manifest Details Error",
					message=f"Error getting manifest from {manifest_link.get('@href', 'unknown')}: {str(e)}"
				)
				continue
		
		return manifests_data

	def get_shipment_manifest(self, shipment="SHIPMENT-00009"):
		doc = frappe.get_doc("Shipment", shipment)
		start_date = datetime.strftime(doc.creation, "%Y%m%d")
		shipment_id = doc.shipments[0].shipment_id
		doctype = "Manifest"
		docname = self.name
		
		cp = CanadaPost()
		#start_date = datetime.strptime(start_date, "%Y-%m-%d").strftime(self.creation, "%Y%m%d")
		end_date = datetime.strftime(datetime.now(), "%Y%m%d")
		url = f"/rs/{cp.settings.customer_number}/{cp.settings.customer_number}/manifest?start={start_date}&end={end_date}"
		headers={'Accept': 'application/vnd.cpc.manifest-v8+xml'}
		response = cp.get_response(url, "", headers=headers, method='GET')
		manifest_links = []
		if isinstance(response["manifests"]["link"], list):
			for manifest in response["manifests"]["link"]:
				manifest_links.append(cp.get_response(manifest["@href"], None, headers={'Accept': manifest["@media-type"]}, method="GET"))
		else:
			manifest = response["manifest"]["link"]
			manifest_links.append(cp.get_response(manifest["@href"], None, headers={'Accept': manifest["@media-type"]}, method="GET"))
		
		shipments = []
		shipment_infos = []
		shipment_found = None
		shipment_ids = []
		for manifest_link in manifest_links:
			if manifest_link is None:
				continue
			for manifest in manifest_link["manifest"]["links"]["link"]:
				if manifest["@rel"] == "manifestShipments":
					manifest_shipments = cp.get_response(manifest["@href"], None, headers={'Accept': manifest["@media-type"]}, method="GET")
					shipments.append(manifest_shipments)
					#return manifest_shipments["shipments"]["link"]
					for shipment in manifest_shipments["shipments"]["link"]:
						not_shipments = ["@rel", "@href", "@media-type"]
						if shipment not in not_shipments:
							shipment_info = cp.get_response(shipment["@href"], None, headers={'Accept': shipment["@media-type"]}, method="GET")
							shipment_infos.append(shipment_info)
							shipment_ids.append(shipment_info["shipment-info"]['shipment-id'])
							if shipment_info["shipment-info"]['shipment-id'] == shipment_id:
								shipment_found = shipment_info
								shipment_manifest = manifest_link
								break
		#Get the manifest
		if shipment_found is not None:
			for link in shipment_manifest["manifest"]["links"]["link"]:
				if link['@rel']=="artifact":
					res = cp.get_response(
							link['@href'], None, {'Accept': link['@media-type'], 'Content-Type': link['@media-type']}, True, 'GET')
					if res.status_code == 200:
						file_name = f"manifest_{shipment_id}.pdf"
						file_path = get_files_path(f"{file_name}", is_private=True)
						with open(file_path, 'wb') as f:
							f.write(res.content)
						file_doc = frappe.new_doc('File')
						file_doc.update({
							'file_name': f"{file_name}",
							'file_url': file_path.replace(frappe.get_site_path(), ''),
							'is_private': 1,
							'folder': 'Home/Attachments',
							'attached_to_doctype': doctype,
							'attached_to_name': docname
						})
						file_doc.insert(ignore_permissions=True)
		return {"shipments": shipment_ids, "found": shipment_found}
		
	def check_shipments(self, shipments):
		all_shipments = []
		available_shipments = []
		response = self.get_response(
							f"/rs/{self.settings.customer_number}/{self.settings.customer_number}/group", "", 
								headers={'Accept': 'application/vnd.cpc.shipment-v8+xml'}, method="GET")
		
		for groups in response["groups"]["group"]:
			if isinstance(groups, list):
				for group in groups:
					all_shipments.append(group["group-id"])
			else:
				all_shipments.append(groups["group-id"])
		for shipment in shipments:
			if shipment in all_shipments:
				available_shipments.append(shipment)
		return available_shipments

	def get_label(self, row, link, fieldname, files):
		res = self.get_response(
			link['@href'], None, {'Accept': link['@media-type'], 'Content-Type': link['@media-type']}, True, 'GET')
		if res.status_code == 200:
			file = self.write_file(
				row, res, f"{fieldname}_{row.shipment_id}.pdf", fieldname)
			row.set(fieldname, file.file_url)
			files.append(file.file_url)

	def write_file(self, doc, res, file_name=None, field_name=None):
		if res.status_code != 200:
			return
		if not file_name:
			file_name = f'{doc.shipment_id}.pdf'
		file_path = get_files_path(f"{file_name}", is_private=True)
		with open(file_path, 'wb') as f:
			f.write(res.content)
			# f.close()
		return self.create_file_doc(file_name, file_path, doc, len(res.content), field_name)

	def create_file_doc(self, file_name, file_path, doc, file_size=0, field_name=None):
		attached_to_doctype = getattr(doc, 'parenttype', doc.doctype)
		attached_to_name = getattr(doc, 'parent', doc.name)
		file_doc = frappe.new_doc('File')
		file_doc.update({
			'file_name': f"{file_name}",
			'file_url': file_path.replace(frappe.get_site_path(), ''),
			'is_private': 1,
			'folder': 'Home/Attachments',
			'attached_to_doctype': attached_to_doctype,
			'attached_to_name': attached_to_name,
			'attached_to_field': field_name,
			'file_size': file_size,
		})
		file_doc.insert(ignore_permissions=True)
		return file_doc

	def avoid_shpment(self, name, shipments_name=[]):
		if isinstance(shipments_name, string_types) and shipments_name.startswith('['):
			shipments_name = ast.literal_eval(shipments_name)

		if len(shipments_name) == 0:
			frappe.throw(_("Please select min one shipment"))
		
		doc = frappe.get_doc('Shipment', name)
		to_be_remove = []
		for shipment in doc.get('shipments', {'name': ('in', shipments_name or [])}):
			url = self.xml_to_json(shipment.tracking_url)
			try:
				res = self.get_response(
					url['link']['@href'],
					None,
					{
						'Accept': url['link']['@media-type'],
						'Content-Type': url['link']['@media-type']
					},
					True,
					'DELETE'
				)

				# If we get a real Response object back
				if hasattr(res, "status_code") and res.status_code == 204:
					to_be_remove.append(shipment)

			except requests.exceptions.HTTPError as e:
				if getattr(e, "response", None) and e.response.status_code == 404:
					frappe.logger().info(
						f"Canada Post void: shipment {shipment.name} not found remotely (404). "
						"Proceeding to remove locally."
					)
					to_be_remove.append(shipment)
				else:
					raise

		for row in to_be_remove:
			doc.remove(row)

		if len(doc.shipments) == 0:
			doc.ais_shipment_status = "Not Shipped"

		doc.save()

		# Set a transient flag so before_cancel knows this came from avoid_shpment
		doc._cancel_from_avoid_shipment = True
		doc.cancel()
		doc._cancel_from_avoid_shipment = False

		delivery_notes = []
		for row in doc.shipment_delivery_note:
			if row.delivery_note not in delivery_notes:
				delivery_notes.append(row.delivery_note)

		for delivery_note in delivery_notes:
			dn = frappe.get_doc("Delivery Note", delivery_note)
			if dn.docstatus == 1:
				dn.cancel()
		return doc.as_dict()

	def get_response(self, url, body, headers=None, return_request=False, method='POST', retry=False, retry_count=0):
		if headers:
			# Double check if charset is set in headers
			ct = headers.get('Content-Type')
			if ct and 'charset=' not in ct.lower():
				headers['Content-Type'] = f'{ct}; charset=utf-8'
			self.sess.headers.update(headers)
		try:
			if isinstance(body, str):
				body = body.encode('utf-8')

			r = self.sess.request(
				method,
				url if url.startswith('https://') else f'{self.settings.host}{url}',
				data=body,
				timeout=30
			)

			# Friendly handling for Canada Post outages
			if r.status_code == 503:
				# If caller wants the raw response, return it
				if return_request:
					return r

				# Show a user-friendly message and stop further parsing
				frappe.throw(
					_("Canada Post is temporarily unavailable. Please wait and try again in a moment."),
					title=_("Canada Post Unavailable")
				)

			# Explicitly handle 404 so caller can decide what to do
			if r.status_code == 404:
				if return_request:
					# still return the raw response if caller asked for it
					return r
				# raise a clear exception for 404
				raise requests.exceptions.HTTPError("404 Not Found", response=r)

			r.raise_for_status()

			if return_request:
				return r
			if r.status_code == 200:
				# Check if content is empty before trying to parse XML
				if not r.content or len(r.content.strip()) == 0:
					return None
				return self.xml_to_json(r.content)

		except (requests.exceptions.SSLError, requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
			# Handle both SSL and timeout errors with retry logic
			if not retry and retry_count < 3:  # Max 3 retries
				# Calculate delay with exponential backoff: 4s, 8s, 16s
				delay = 4 * (2 ** retry_count)
				error_type = "SSL" if isinstance(e, requests.exceptions.SSLError) else "Timeout"
				frappe.logger().info(f"{error_type} Error, retrying in {delay} seconds...")
				time.sleep(delay)
				return self.get_response(url, body, headers, return_request, method, True, retry_count + 1)
			else:
				frappe.log_error(
					f"Max retries reached for {url}. Error: {str(e)}",
					"Canada Post API Error"
				)
				raise
		except Exception as e:
			# If this is an HTTPError with a 404, re‑raise so caller
			# can handle it specially, instead of building XML error messages.
			if isinstance(e, requests.exceptions.HTTPError) and getattr(e, "response", None) and e.response.status_code == 404:
				raise

			if 'r' not in locals():
				frappe.throw(frappe.get_traceback())
			res = r.content
			error_code = None
			try:
				content = self.xml_to_json(res)
				if content and isinstance(content.get('messages', {}).get('message'), (dict, list)):
					if isinstance(content['messages']['message'], dict):
						content['messages']['message'] = [
							content['messages']['message']]
					error_code = content["messages"]["message"][0].get("code")
					
					# Transform XML validation errors into user-friendly messages
					for i, message in enumerate(content['messages']['message']):
						description = message.get('description', '')
						
						# Handle common XML validation errors
						if 'cvc-simple-type' in description:
							# Extract field name from error
							field_match = re.search(r'element.*?\}([a-zA-Z-]+)', description)
							if field_match:
								field_name = field_match.group(1)
								
								# Map XML field names to user-friendly names
								field_mapping = {
									'prov-state': 'Province/State',
									'postal-zip-code': 'Postal/ZIP Code',
									'city': 'City',
									'country-code': 'Country',
									'address-line-1': 'Address Line 1',
									'name': 'Name',
									'phone': 'Phone Number',
									'address-line-2': 'Address Line 2',
									'company': 'Company Name',
									'client-id': 'Client ID'
								}
								
								friendly_field = field_mapping.get(field_name, field_name.replace('-', ' ').title())
								
								if 'may not be empty' in description:
									content['messages']['message'][i]['description'] = f"The {friendly_field} field is required but was empty."
								elif 'is not valid' in description:
									content['messages']['message'][i]['description'] = f"The {friendly_field} field has an invalid format."
								elif 'length must be' in description:
									length_match = re.search(r'length must be ([0-9]+)', description)
									if length_match:
										length = length_match.group(1)
										content['messages']['message'][i]['description'] = f"The {friendly_field} field must be exactly {length} characters long."
					
					# Create a formatted HTML table of errors
					res = frappe.render_template("""
						<table class="table table-bordered">
						<tr>
							<th>Error</th>
							<th>Description</th>
						</tr>
						{% for message in messages.message %}
						<tr>
							<th>{{ message.code if message.code else "Validation Error" }} </th>
							<td>{{ message.description }} </td>
						</tr>
						{% endfor %}
						</table>
					""", content)
			except Exception as parse_error:
				frappe.log_error(f"Error parsing Canada Post response: {str(parse_error)}", "Canada Post Error")
				
				# Handle unparseable responses
				if isinstance(res, bytes):
					try:
						res = res.decode('utf-8')
					except:
						res = "Unable to decode response from Canada Post"
				
				# Try to extract meaningful information from unparsed response
				if isinstance(res, str) and 'cvc-simple-type' in res:
					res = self.convert_validation_error_to_friendly_message(res)
			
			# If error code is 9122 then it means the manifest is already created, get the manifest
			if error_code is not None and error_code == "9122":
				raise ValueError("9122")
			else:
				frappe.throw(
					res, title=f"Canada Post Shipping Error")
				
	def convert_validation_error_to_friendly_message(self, error_text):
		"""Convert technical XML validation errors to user-friendly messages"""
		
		# Common error patterns and their user-friendly versions
		if 'prov-state' in error_text and 'may not be empty' in error_text:
			return "The Province/State field is required but was empty. Please check both the delivery and pickup addresses."
		
		elif 'postal-zip-code' in error_text:
			if 'may not be empty' in error_text:
				return "The Postal/ZIP Code is required but was empty. Please check both addresses."
			else:
				return "The Postal/ZIP Code format is invalid. For Canadian addresses, use format 'A1A 1A1'. For US addresses, use '12345' or '12345-6789'."
		
		elif 'city' in error_text and 'may not be empty' in error_text:
			return "The City field is required but was empty. Please check both the delivery and pickup addresses."
		
		elif 'country-code' in error_text:
			return "The Country field is invalid or empty. Please use a valid two-letter country code (CA for Canada, US for United States)."
		
		elif 'address-line-1' in error_text and 'may not be empty' in error_text:
			return "The Address Line 1 field is required but was empty. Please check both the delivery and pickup addresses."
		
		# If no specific pattern matched, provide a general message
		return "There was a validation error with the address information. Please verify that all required fields are filled out correctly."