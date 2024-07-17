import frappe
import requests
from frappe import _, get_desk_link, bold
import xmltodict
from requests.auth import _basic_auth_str
from frappe.utils import get_files_path
from six import string_types
import ast
from PyPDF2 import PdfFileMerger
from datetime import datetime


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

	def set_default_headers(self):
		self.sess.headers = {
			'Accept': 'application/vnd.cpc.shipment-v8+xml',
			'Content-Type': 'application/vnd.cpc.shipment-v8+xml',
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
		delivery_address_doc.state = get_state_code(delivery_address_doc.state)
		pickup_address_doc = frappe.get_doc(
			'Address', doc.pickup_address_name).as_dict()
		
		if pickup_address_doc.state is None or pickup_address_doc.state == "":
			frappe.throw(f"State needed in billing address {pickup_address_doc.name}.")

		if pickup_address_doc.pincode is None or pickup_address_doc.pincode == "":
			frappe.throw(f"Postal code needed in billing address {pickup_address_doc.name}")

		if len(pickup_address_doc.state) > 2:
			pickup_address_doc.state = get_state_code(pickup_address_doc.state)
		pickup_person_doc = frappe.get_doc(
			'User', doc.pickup_contact_person).as_dict()
		delivery_contact_doc = frappe.get_doc(
			'Contact', doc.delivery_contact_name).as_dict()
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
			body = frappe.render_template(
				"metactical/utils/shipping/templates/canada_post/request/get_rate.xml", context)
			response = self.get_response("/rs/ship/price", body, {'Accept': 'application/vnd.cpc.ship.rate-v4+xml',
																  'Content-Type': 'application/vnd.cpc.ship.rate-v4+xml'})
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

	def create_shipping(self, name, carrier_service):
		if carrier_service is None:
			frappe.throw(_("Service Code Required. please select service"))
		if isinstance(carrier_service, string_types) and carrier_service.startswith('{'):
			carrier_service = ast.literal_eval(carrier_service)
		files = []
		doc = frappe.get_doc('Shipment', name)
		context = self.get_context(name)
		exists = self.existing_shipments(context.doc)
		pickup_date = datetime.strftime(doc.pickup_date, "%Y%m%d")
		context.pickup_date = pickup_date
		context.group_id = f'{doc.warehouse.split("-")[0].replace(" ", "")}-{pickup_date}'
		for parcel in context.doc.shipment_parcel:
			context.parcel = parcel
			context.parcel.carrier_service = carrier_service.get(parcel.name)
			for c in range(parcel.count - exists.get(parcel.name, 0)):
				body = frappe.render_template(
					"metactical/utils/shipping/templates/canada_post/request/create_shipment.xml", context)
				response = self.get_response(
					f"/rs/{self.settings.customer_number}/{self.settings.customer_number}/shipment", body, {'Accept': 'application/vnd.cpc.shipment-v8+xml',
																									   'Content-Type': 'application/vnd.cpc.shipment-v8+xml'})
				row = doc.append('shipments', {
					'shipment_id': response['shipment-info']['shipment-id'],
					'awb_number': response['shipment-info']['tracking-pin'],
					'service_provider': 'Canada Post',
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
		# Merger PDFs.
		if files:
			files = [self.pdf_merge(files, doc).file_url]
		return files

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
		context.group = f'{doc.warehouse.split("-")[0].replace(" ", "")}-{datetime.strftime(doc.pickup_date, "%Y%m%d")}'
		context.warehouse_doc = frappe.get_doc('Warehouse', doc.warehouse)
		context.warehouse_doc.state = get_state_code(context.warehouse_doc.state)
		body = frappe.render_template(
			"metactical/utils/shipping/templates/canada_post/request/transmit_shipment.xml", context)
		response = self.get_response(
				f"/rs/{self.settings.customer_number}/{self.settings.customer_number}/manifest", body, headers={'Accept': 'application/vnd.cpc.manifest-v8+xml', 'Content-Type': 'application/vnd.cpc.manifest-v8+xml'})
		
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
								file_name = f"{manifest}.pdf"
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
							
	
	def get_shipment_manifest(shipment="SHIPMENT-00009"):
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
		file_doc = frappe.new_doc('File')
		file_doc.update({
			'file_name': f"{file_name}",
			'file_url': file_path.replace(frappe.get_site_path(), ''),
			'is_private': 1,
			'folder': 'Home/Attachments',
			'attached_to_doctype': doc.parenttype,
			'attached_to_name': doc.parent,
			'attached_to_field': field_name,
			'file_size': file_size,
		})
		file_doc.insert(ignore_permissions=True)
		return file_doc

	def avoid_shpment(self, name, shipments_name):
		if not shipments_name:
			frappe.throw(_("Please select min one shipment"))
		if isinstance(shipments_name, string_types) and shipments_name.startswith('['):
			shipments_name = ast.literal_eval(shipments_name)
		doc = frappe.get_doc('Shipment', name)
		to_be_remove = []
		for shipment in doc.get('shipments', {'name': ('in', shipments_name or [])}):
			url = self.xml_to_json(shipment.tracking_url)
			res = self.get_response(url['link']['@href'], None, {
									'Accept': url['link']['@media-type'], 'Content-Type': url['link']['@media-type']}, True, 'DELETE')
			if res.status_code == 204:
				to_be_remove.append(shipment)
		for row in to_be_remove:
			doc.remove(row)
		doc.ais_shipment_status = "Not Shipped"
		doc.save()
		return doc.as_dict()

	def get_response(self, url, body, headers=None, return_request=False, method='POST', retry=False):
		if headers:
			self.sess.headers.update(headers)
		try:
			r = self.sess.request(method, url if url.startswith(
				'https://') else f'{self.settings.host}{url}', data=body)
			r.raise_for_status()
			if return_request:
				return r
			if r.status_code == 200:
				return self.xml_to_json(r.content)
		except requests.exceptions.SSLError:
			if not retry:
				self.get_response(url, body, headers,
								  return_request, method, True)
		except:
			if 'r' not in locals():
				frappe.throw(frappe.get_traceback())
			res = r.content
			error_code = None
			try:
				content = self.xml_to_json(res)
				if content and isinstance(content['messages']['message'], (dict, list)):
					if isinstance(content['messages']['message'], dict):
						content['messages']['message'] = [
							content['messages']['message']]
					error_code = content["messages"]["message"][0]["code"]	
					res = frappe.render_template("""
						<table class="table table-bordered">
						<tr>
							<th>Code</th>
							<th> Description </th>
						</tr>
						{% for message in messages.message %}
						<tr>
							<th>{{ message.code }} </th>
							<td>{{ message.description }} </td>
						{% endfor %}
						</table>
					""", content)
			except:
				pass
			
			# If error code is 9122 then get means the manifest is already created, get the manifest
			if error_code is not None and error_code == "9122":
				raise ValueError("9122")
			else:
				frappe.throw(
					res, title=f"Error from Provider Server, Code: {r.status_code}")


def get_state_code(state):
	symbol = frappe.db.get_value('City Symbol', {"city": state}, "symbol")
	return symbol
