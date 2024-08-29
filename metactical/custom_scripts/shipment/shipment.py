import frappe
from frappe import _
from metactical.utils.shipping.shipping import avoid_shpment
from metactical.utils.shipping.canada_post import CanadaPost
from datetime import datetime
from frappe.utils import get_files_path

def validate(doc, method=None):
	for parcel in doc.shipment_parcel:
		if parcel.weight > 32:
			frappe.msgprint(_("Weight doesn't allow more than 32 Kg"))


def before_cancel(doc, method=None):
	if doc.shipments:
		avoid_shpment(doc.name, doc.service_provider, [x.name for x in doc.shipments])
		
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
	
