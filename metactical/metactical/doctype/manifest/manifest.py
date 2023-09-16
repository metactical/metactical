# Copyright (c) 2023, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe import _
from metactical.utils.shipping.canada_post import CanadaPost
from datetime import datetime


class Manifest(Document):
	pass
						

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
	doc.status = "Completed"
	doc.save()
	return {"po_number": po_number, "shipments": shipments}
			
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
