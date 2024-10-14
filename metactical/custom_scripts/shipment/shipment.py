import frappe
from frappe import _
from metactical.utils.shipping.shipping import avoid_shpment
from metactical.utils.shipping.canada_post import CanadaPost
from datetime import datetime
from frappe.utils import get_files_path
from erpnext.stock.doctype.shipment.shipment import Shipment

class CustomShipment(Shipment):
	# def before_save(self):
	# 	delivery_notes = self.

	def validate(self):
		super(CustomShipment, self).validate()
		for parcel in self.shipment_parcel:
			if parcel.weight > 32:
				frappe.msgprint(_("Weight doesn't allow more than 32 Kg"))

		self.update_shipment_parcel()
		
	def update_shipment_parcel(self):
		shipment_parcels = self.shipment_parcel
		delivery_notes = self.shipment_delivery_note

		# remove duplicate delivery notes
		delivery_notes = list({dn.delivery_note: dn for dn in delivery_notes}.values())

		old_doc = self.get_doc_before_save()
		old_delivery_notes = old_doc.shipment_delivery_note if old_doc else []

		new_shipment_parcels = []
		for dn in delivery_notes:
			packing_slips = frappe.get_all("Packing Slip", filters={"delivery_note": dn.delivery_note, "docstatus": 1}, 
											fields=["name", "from_case_no", "gross_weight_pkg", "custom_neb_box_length", "custom_neb_box_width", "custom_neb_box_height"])

			for ps in packing_slips:
				found = False
				for sp in shipment_parcels:
					if sp.custom_neb_box == ps.from_case_no and sp.custom_neb_delivery_note == dn.delivery_note:
						found = True
						break
				
				if not found:
					new_shipment_parcels.append({
						"parent": self.name,
						"parentfield": "shipment_parcel",
						"parenttype": "Shipment",
						"custom_neb_box": ps.from_case_no,
						"custom_neb_delivery_note": dn.delivery_note,
						"weight": ps.gross_weight_pkg,
						"length": ps.custom_neb_box_length,
						"width": ps.custom_neb_box_width,
						"height": ps.custom_neb_box_height,
						"count": 1
					})
			
		if new_shipment_parcels:
			shipment_parcels += new_shipment_parcels

		if old_delivery_notes:
			for old_dn in old_delivery_notes:
				if old_dn.delivery_note not in [dn.delivery_note for dn in delivery_notes]:
					shipment_parcels = [sp for sp in shipment_parcels if sp.custom_neb_delivery_note != old_dn.delivery_note]
						
		for i, sp in enumerate(shipment_parcels):
			if type(sp) == dict:
				sp["idx"] = i+1
			else:
				sp.idx = i+1

		self.update({"shipment_parcel": shipment_parcels})

	def before_cancel(self):
		if self.shipments:
			avoid_shpment(self.name, self.service_provider, [x.name for x in self.shipments])

	def on_submit(self):
		# Metactical Customization: Allow 0 value goods to be shipped
		if not self.shipment_parcel:
			frappe.throw(_("Please enter Shipment Parcel information"))
		'''if self.value_of_goods == 0:
			frappe.throw(_("Value of goods cannot be 0"))'''
		self.db_set("status", "Submitted")
		
def set_source_and_customer_po(doc):
	doc.neb_source = None
	doc.neb_customer_po_number = None

	if doc.shipment_delivery_note:
		for row in doc.shipment_delivery_note:
			if not doc.neb_source and row.neb_source:
				doc.neb_source = row.neb_source
			if not doc.neb_customer_po_number and row.neb_order_id:
				doc.neb_customer_po_number = row.neb_order_id

			if doc.neb_source and doc.neb_customer_po_number:
				break


@frappe.whitelist()
def get_manifest(start_date, shipment_id, doctype, docname):
	cp = CanadaPost()
	start_date = datetime.strptime(start_date, "%Y-%m-%d").strftime("%Y%m%d")
	frappe.errprint(start_date)
	frappe.errprint(shipment_id)
	#end_date = datetime.strftime(datetime.now(), "%Y%m%d")
	end_date = start_date
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
	
