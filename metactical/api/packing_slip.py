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
		skip = False
		if "item_code" in item and item["item_code"]:
			item_doc = frappe.get_doc('Item', item["item_code"])
			item["image"] = item_doc.get('image')
			barcodes = []
			if item_doc.get('barcodes') is not None:
				for barcode in item_doc.barcodes:
					barcodes.append(barcode.barcode)
			item["ifw_retailskusufix"] = item_doc.get("ifw_retailskusuffix")
			item["item_barcode"] = barcodes
			item["shipping_height"] = item_doc.get("ais_shipping_height") or 0
			item["shipping_width"] = item_doc.get("ais_shipping_width") or 0
			item["shipping_length"] = item_doc.get("ais_shipping_length") or 0
			item["weight"] = item_doc.get("weight_per_unit") or 0
			item["s_warehouse"] = item.get("s_warehouse") or ""
			item["t_warehouse"] = item.get("t_warehouse") or ""

			# Detect product bundles and attach sub-items for scanning
			is_bundle = frappe.db.exists('Product Bundle', item["item_code"])
			item["is_bundle"] = bool(is_bundle)
			item["bundle_items"] = []

			if is_bundle and item.get("dn_detail"):
				delivery_note = frappe.db.get_value('Delivery Note Item', item["dn_detail"], 'parent')
				if delivery_note:
					packed_items = frappe.db.get_all(
						'Packed Item',
						filters={
							'parent': delivery_note,
							'parent_item': item["item_code"],
							'parent_detail_docname': item["dn_detail"]
						},
						fields=['name', 'item_code', 'item_name', 'qty', 'packed_qty', 'warehouse']
					)
					bundle_items_list = []
					for pi in packed_items:
						remaining = float(pi.get('qty') or 0) - float(pi.get('packed_qty') or 0)
						if remaining <= 0:
							continue
						pi_item_doc = frappe.get_doc('Item', pi['item_code'])
						pi_barcodes = [b.barcode for b in (pi_item_doc.barcodes or [])]
						bundle_items_list.append({
							'name': pi['name'],
							'item_code': pi['item_code'],
							'item_name': pi['item_name'],
							'qty': remaining,
							'scanned_qty': 0,
							'item_barcode': pi_barcodes,
							'image': pi_item_doc.get('image'),
							'ifw_retailskusufix': pi_item_doc.get('ifw_retailskusuffix'),
							'warehouse': pi.get('warehouse') or '',
						})

					item["bundle_items"] = bundle_items_list

					# All sub-items fully packed — exclude bundle from pending list
					if not bundle_items_list:
						skip = True

		if not skip:
			temp_items.append(item)

	return temp_items