import frappe
from erpnext.stock.doctype.packing_slip.packing_slip import PackingSlip
from frappe.utils import cint, flt

class CustomPackingSlip(PackingSlip):
	def on_submit(self):
		#Clear associated tote if any
		tote_exists = frappe.db.exists('Picklist Tote', {'current_delivery_note': self.delivery_note})
		if tote_exists:
			docname = frappe.db.get_value('Picklist Tote', {'current_delivery_note': self.delivery_note})
			doc = frappe.get_doc('Picklist Tote', docname)
			doc.update({
				'current_delivery_note': '',
				'used_by': '',
				'tote_items': []
			})
			doc.save(ignore_permissions=True)
			
	@frappe.whitelist()
	def get_items(self):
		self.set("items", [])

		custom_fields = frappe.get_meta("Delivery Note Item").get_custom_fields()

		dn_details = self.get_details_for_packing()[0]
		shipping_items = frappe.get_all('Pick List Shipping Item', pluck='item')
		for item in dn_details:
			if flt(item.qty) > flt(item.packed_qty) and item.item_code not in shipping_items:
				ch = self.append("items", {})
				ch.item_code = item.item_code
				ch.item_name = item.item_name
				ch.stock_uom = item.stock_uom
				ch.description = item.description
				ch.batch_no = item.batch_no
				ch.qty = flt(item.qty) - flt(item.packed_qty)

				# copy custom fields
				for d in custom_fields:
					if item.get(d.fieldname):
						ch.set(d.fieldname, item.get(d.fieldname))

		self.update_item_details()
