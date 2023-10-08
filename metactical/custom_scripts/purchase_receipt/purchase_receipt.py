import frappe
from erpnext.stock.doctype.purchase_receipt.purchase_receipt import PurchaseReceipt
from frappe.utils import flt, cstr, now, get_datetime_str, file_lock, date_diff, now_datetime, cint
from frappe import _, msgprint, is_whitelisted

class CustomPurchaseReceipt(PurchaseReceipt):
	def validate(self):
		super(CustomPurchaseReceipt, self).validate()
		if self.purchase_order:
			for d in self.items:
				d.purchase_order = self.purchase_order
				d.purchase_order_item = frappe.db.get_value("Purchase Order Item", {"item_code": d.item_code, "parent": d.purchase_order}, "name")
				if not d.purchase_order_item:
					frappe.throw("Purchase Order Missing for Item {} at Row {}".format(d.item_code, str(d.idx)))
	
	def submit(self):
		if len(self.items) > 100:
			msgprint(
				_(
					"The task has been enqueued as a background job. In case there is any issue on processing in background, the system will add a comment about the error on this document and revert to the Draft stage"
				)
			)
			self.queue_action("submit", timeout=2000)
		else:
			self._submit()
	
	def queue_action(self, action, **kwargs):
		"""Run an action in background. If the action has an inner function,
		like _submit for submit, it will call that instead"""
		# call _submit instead of submit, so you can override submit to call
		# run_delayed based on some action
		# See: Stock Reconciliation
		from frappe.utils.background_jobs import enqueue

		if hasattr(self, '_' + action):
			action = '_' + action

		if file_lock.lock_exists(self.get_signature()):
			frappe.throw(_('This document is currently queued for execution. Please try again'),
				title=_('Document Queued'))
		
		frappe.db.set_value(self.doctype, self.name, 'ais_queue_status', 'Queued',  update_modified=False)
		frappe.db.set_value(self.doctype, self.name, 'ais_queued_date', now_datetime(),  update_modified=False)
		frappe.db.set_value(self.doctype, self.name, 'ais_queued_by', frappe.session.user,  update_modified=False)
		self.lock()
		enqueue('metactical.custom_scripts.frappe.document.execute_action', doctype=self.doctype, name=self.name,
			action=action, **kwargs)

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
