# Copyright (c) 2025, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class ShipmentSettings(Document):
	pass

@frappe.whitelist()
def get_default_services():
	default_shipping_service = None
	default_carrier_service = None
	
	settings = frappe.get_doc("Shipment Settings")
	if settings.default_shipping_service and settings.default_shipping_service != "":
		if settings.default_shipping_service == "Purolator":
			default_shipping_service = settings.default_shipping_service
			default_carrier_service = settings.default_purolator_service
		elif settings.default_shipping_service == "Canada Post":
			cp_services = {
				"Regular Parcel": "DOM.RP",
				"Expedited Parcel": "DOM.EP",
				"Xpresspost": "DOM.XP",	
				"Priority": "DOM.PC",
				"Library Books": "DOM.LIB",	
				"Expedited Parcel USA": "USA.EP	",
				"Small Packet USA Air": "USA.SP.AIR",
				"Tracked Packet – USA": "USA.TP",
				"Tracked Packet – USA (LVM)": "USA.TP.LVM",
				"Xpresspost USA": "USA.XP",	
				"Xpresspost International": "INT.XP",	
				"International Parcel Air": "INT.IP.AIR",	
				"International Parcel Surface": "INT.IP.SURF",
				"Small Packet International Air": "INT.SP.AIR",
				"Small Packet International Surface": "INT.SP.SURF",
				"Tracked Packet – International": "INT.TP"
			}
			default_shipping_service = settings.default_shipping_service
			default_carrier_service = cp_services[settings.default_cp_service]
	return {"default_shipping_service": default_shipping_service, "default_carrier_service": default_carrier_service}