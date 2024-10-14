import frappe
from frappe.utils import flt, cstr, now, get_datetime_str, file_lock, date_diff, now_datetime
from frappe import _, msgprint, is_whitelisted
from erpnext.stock.doctype.stock_reconciliation.stock_reconciliation import StockReconciliation

class CustomStockReconciliation(StockReconciliation):	
	def submit(self):
		frappe.throw("test")
		if len(self.items) > 10:
			msgprint(
				_(
					"The task has been enqueued as a background job. In case there is any issue on processing in background, the system will add a comment about the error on this Stock Reconciliation and revert to the Draft stage"
				)
			)

			print(self.creation)
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

		frappe.log_error(title="aa", message=self.creation)

		if file_lock.lock_exists(self.get_signature()):
			frappe.throw(_('This document is currently queued for execution. Please try again'),
				title=_('Document Queued'))
		
		frappe.db.set_value(self.doctype, self.name, 'ais_queue_status', 'Queued',  update_modified=False)
		frappe.db.set_value(self.doctype, self.name, 'ais_queued_date', now_datetime(),  update_modified=False)
		frappe.db.set_value(self.doctype, self.name, 'ais_queued_by', frappe.session.user,  update_modified=False)
		self.lock()
		enqueue('metactical.custom_scripts.frappe.document.execute_action', doctype=self.doctype, name=self.name,
			action=action, **kwargs)
