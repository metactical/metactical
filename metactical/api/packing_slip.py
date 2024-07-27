import frappe
import json


@frappe.whitelist()
def fetch_item(barcode):
    item_code = frappe.db.get_value('Item Barcode', barcode, 'parent')
    if item_code:
        return item_code
    else:
        return False


@frappe.whitelist()
def get_item_master(items):
	'''
	getting extra fields for packing slip items display
	'''
	items = json.loads(items)
	
	if len(items) == 0:
		return items
		
	temp_items = []
	for item in items:
		if "item_code" in item and item["item_code"]:
			item_doc = frappe.get_doc('Item', item["item_code"])
			item["image"] = item_doc.get('image')
			barcodes = []
			if item_doc.get('barcodes') is not None:
				for barcode in item_doc.barcodes:
					barcodes.append(barcode.barcode)
			item["item_barcode"] = barcodes
			item["shipping_height"] = item_doc.get("ais_shipping_height")
			item["shipping_width"] = item_doc.get("ais_shipping_width")
			item["shipping_length"] = item_doc.get("ais_shipping_length")
			item["weight"] = item_doc.get("weight_per_unit")
		temp_items.append(item)
		
	return temp_items
