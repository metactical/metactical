import frappe
from erpnext.stock.doctype.purchase_receipt.purchase_receipt import PurchaseReceipt
from frappe.utils import flt, cstr, now, get_datetime_str, file_lock, date_diff, now_datetime, cint
from frappe import _, msgprint, is_whitelisted
from metactical.custom_scripts.utils.metactical_utils import queue_action
from frappe.model.docstatus import DocStatus

class CustomPurchaseReceipt(PurchaseReceipt):
	def validate(self):
		super(CustomPurchaseReceipt, self).validate()
		if self.purchase_order:
			for d in self.items:
				d.purchase_order = self.purchase_order

		self.validate_barcodes()
    
	def validate_barcodes(self):
		for item in self.items:
			if not item.barcode:
				barcode = frappe.db.get_value("Item Barcode", {"parent": item.item_code}, "barcode")
				if barcode:	
					item.barcode = barcode
     
	def save(self):
		if self.docstatus == DocStatus.submitted() and len(self.items) > 100 and \
			self.ais_queue_status and self.ais_queue_status != "Queued":
			msgprint(
				_(
					"The task has been enqueued as a background job. In case there is \
					any issue on processing in background, the system will add a comment \
					about the error on this document and revert to the Draft stage"
				)
			)
			queue_action(self, "submit", timeout=2000)
		else:
			super().save()

	def before_submit(self):
		self.barcode_check()

	def barcode_check(self):
		for item in self.items:
			barcode_exists = frappe.db.exists("Item Barcode", {"parent": item.item_code})
			if not barcode_exists:
				frappe.throw(f"Error: Please add a barcode for item {item.item_code}")

def validate(self, method):
	if self.set_warehouse:
		for item in self.items:
			if item.warehouse != self.set_warehouse:
				item.warehouse = self.set_warehouse
			
@frappe.whitelist()
def get_pr_items(docname):
	items = []
	added_items = []
	doc = frappe.get_doc('Purchase Receipt', docname)
	for item in doc.items:
		if item.item_code not in added_items:
			items.append(item)
			added_items.append(item.item_code)
		else:
			for i in items:
				if i.item_code == item.item_code:
					i.update({
						'qty': i.qty + item.qty
					})
	return items


@frappe.whitelist()
def get_print_format(docname):
	doc = frappe.get_doc('Purchase Receipt', docname)
	return frappe.get_print(doctype=doc.doctype, name=doc.name, print_format="Purchase Receipt Barcode - V2", no_letterhead=0)