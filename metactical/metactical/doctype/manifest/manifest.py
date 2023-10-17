# Copyright (c) 2023, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe import _
from metactical.utils.shipping.canada_post import CanadaPost
from datetime import datetime
from frappe.utils import get_files_path


class Manifest(Document):
	pass
						
@frappe.whitelist()
def create_manifest(manifest):
	try:
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
		doc.status = "Completed"
		doc.save()
		return {"po_number": po_number, "shipments": shipments}
	except ValueError as e:
		if str(e) == "9122":
			redownload_manifest(manifest)

@frappe.whitelist()		
def redownload_manifest(docname="MF-10-11-2023-251", doctype="Manifest"):
	doc = frappe.get_doc(doctype, docname)
	ref_shipments = []
	for row in doc.items:
		ref_shipments.append(row.shipment_id)
	cp = CanadaPost()
	date = doc.pickup_date.strftime("%Y%m%d")
	url = f"/rs/{cp.settings.customer_number}/{cp.settings.customer_number}/manifest?start={date}&end={date}"
	headers={'Accept': 'application/vnd.cpc.manifest-v8+xml'}
	response = cp.get_response(url, "", headers=headers, method='GET')
	manifest_links = []
	if isinstance(response["manifests"]["link"], list):
		for manifest in response["manifests"]["link"]:
			manifest_links.append(cp.get_response(manifest["@href"], None, headers={'Accept': manifest["@media-type"]}, method="GET"))
	else:
		manifest = response["manifests"]["link"]
		manifest_links.append(cp.get_response(manifest["@href"], None, headers={'Accept': manifest["@media-type"]}, method="GET"))
	
	shipments = []
	shipment_infos = []
	shipments_found = {}
	shipment_ids = []
	shipment_manifests = []
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
						if shipment_info["shipment-info"]['shipment-id'] in ref_shipments:
							shipments_found.update({
								shipment_info["shipment-info"]['shipment-id']: shipment_info["shipment-info"]["po-number"]
							})
							if manifest_link not in shipment_manifests:
								shipment_manifests.append(manifest_link)
	
	#Get the manifest
	if len(shipments_found) > 0:
		for shipment_manifest in shipment_manifests:
			for link in shipment_manifest["manifest"]["links"]["link"]:
				if link['@rel']=="artifact":
					res = cp.get_response(
							link['@href'], None, {'Accept': link['@media-type'], 'Content-Type': link['@media-type']}, True, 'GET')
					if res.status_code == 200:
						file_name = f"manifest_{docname}.pdf"
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
						
		#Update the shipments
		doc.items = []
		for shipment, po_number in shipments_found.items():
			exists = frappe.db.exists("Canada Post Shipment", {"shipment_id": shipment})
			if exists:
				shipment_name = frappe.db.get_value("Canada Post Shipment", {"shipment_id": shipment}, "parent")
				frappe.db.set_value("Shipment", shipment_name, "po_number", po_number)
				doc.append("items", {
					"shipment": shipment_name,
					"shipment_id": shipment,
					"status": "Transmitted"
				})
				doc.po_number = po_number
		doc.status = "Completed"
		doc.save()
	
	return {"shipments": shipment_ids, "found": shipments_found}

@frappe.whitelist()
def get_shipments(pickup_date, warehouse):
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
		pickup_contact_person = shipments[0].pickup_contact_person
	return {
		"shipments": shipments,
		"pickup_contact_person": pickup_contact_person
	}

@frappe.whitelist()
def get_warehouse_address(warehouse):
	warehouse_address = None
	address = frappe.db.sql("""
				SELECT
					address.name AS warehouse_address
				FROM
					`tabDynamic Link` AS link
				LEFT JOIN
					`tabAddress` AS address ON link.parenttype = 'Address' AND link.parent = address.name
				WHERE
					link.link_doctype = "Warehouse" AND link.link_name = %(warehouse)s
				""", {"warehouse": warehouse}, as_dict=1)
				
	if len(address) > 0:
		warehouse_address = address[0].warehouse_address
	return warehouse_address
