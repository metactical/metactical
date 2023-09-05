# Copyright (c) 2023, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe import _
from metactical.utils.shipping.canada_post import CanadaPost
from datetime import datetime


class Manifest(Document):
	#def validate(self):
	#	self.sync_warehouse()
	
	def sync_warehouse(self):
		warehouses = set(x.warehouse for x in self.get('items', default=[]) if x.warehouse)
		# Remove Unwanted Address.
		exists = []
		to_be_remove = []
		for x in self.get('manifests', default=[]):
			exists.append(x.warehouse)
			if x.warehouse not in warehouses:
				to_be_remove.append(x)
		for rx in to_be_remove:
			self.remove(rx)
		# Added new on
		for warehosue in warehouses:
			if warehosue not in exists:
				self.append('manifests', {'warehouse': warehosue})

	'''@frappe.whitelist()
	def get_shipments(self):
		rows = frappe.get_all('Shipment', [['pickup_date', '=', self.pickup_date], ['Canada Post Shipment', 'shipment_id', 'is', 'set']],
								  ['name as shipment', '`tabCanada Post Shipment`.name as row_name', '`tabCanada Post Shipment`.shipment_id'])
		existings = frappe.get_all('Manifest Item', [['shipment_id', 'in', [x.shipment_id for x in rows]]], pluck='shipment_id')
		for row in rows:
			if row.shipment_id in existings:
				continue
			self.append('items', row)
		return self.as_dict()'''
		

	@frappe.whitelist()
	def create_manifest(self):
		cp = CanadaPost()
		files = []
		for warehouse in self.get('manifests', default=[]):
			if warehouse.manifest:
				continue
			items = [x.shipment for x in self.get('items', {'warehouse': warehouse.warehouse})]
			if items:
				#available_shipments = cp.check_shipments(items)
				available_shipments = items
				# Create manifest for available shipments
				if len(available_shipments) > 0:
					try:
						files.extend(cp.create_manifest(available_shipments, self, warehouse))
					except ValueError as exp:
							if str(exp) == "9122":
								#frappe.errprint("Throws 1922")
								# Get existing manifests for previous shipments
								for item in items:
									self.get_shipment_manifest(item)
				
		self.save()
		return files

	@frappe.whitelist()
	def get_shipment_manifest(self, shipment):
		doc = frappe.get_doc("Shipment", shipment)
		start_date = datetime.strftime(doc.creation, "%Y%m%d")
		shipment_id = doc.shipments[0].shipment_id
		doctype = "Manifest"
		docname = self.name
		#frappe.errprint("Got here")
		cp = CanadaPost()
		#start_date = datetime.strptime(start_date, "%Y-%m-%d").strftime(self.creation, "%Y%m%d")
		end_date = datetime.strftime(datetime.now(), "%Y%m%d")
		#end_date = "20230825"
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
		frappe.errprint({"manifest": manifest_links})
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
		frappe.errprint({"shipments": shipment_ids, "found": shipment_found})

@frappe.whitelist()
def create_manifest(manifest):
	cp = CanadaPost()
	shipments, po_number = cp.create_manifest(manifest)
	doc = frappe.get_doc("Manifest", manifest)
	doc.po_number = po_number
	
	# Update shipments
	doc.items = []
	for shipment in shipments:
		exists = frappe.db.exists("Canada Post Shipment", {"shipment_id": shipment})
		if exists:
			shipment_name = frappe.db.get_value("Canada Post Shipment", {"shipment_id": shipment}, "parent")
			frappe.db.set_value("Shipment", shipment_name, "po_number", po_number)
			doc.append("items", {
				"shipment": shipment_name,
				"shipment_id": shipment,
				"status": "Transmitted"
			})
	doc.save()
	return {"po_number": po_number, "shipments": shipments}
			
@frappe.whitelist()
def get_shipments(pickup_date, warehouse):
	pickup_company = None
	pickup_address_name = None
	pickup_contact_person = None
	shipments = frappe.db.sql("""
					SELECT
						shipment.name AS shipment_name, cps.shipment_id, shipment.pickup_company,
						shipment.pickup_address_name, shipment.pickup_contact_person
					FROM
						`tabCanada Post Shipment` AS cps
					LEFT JOIN
						`tabShipment` AS shipment ON shipment.name = cps.parent
					WHERE
						shipment.po_number IS NULL AND shipment.pickup_date = %(pickup_date)s
						AND warehouse = %(warehouse)s
				""", {"pickup_date": pickup_date, "warehouse": warehouse}, as_dict=1)
	if len(shipments) > 0:
		pickup_company = shipments[0].pickup_company
		pickup_address_name = shipments[0].pickup_address_name
		pickup_contact_person = shipments[0].pickup_contact_person
	return {
		"shipments": shipments,
		"pickup_company": pickup_company,
		"pickup_address_name": pickup_address_name,
		"pickup_contact_person": pickup_contact_person
	}
