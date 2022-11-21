import frappe
from erpnext.stock.doctype.packing_slip.packing_slip import PackingSlip

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
