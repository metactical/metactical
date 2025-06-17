import frappe
from frappe.utils import flt, cstr, now, get_datetime_str, file_lock, date_diff, now_datetime
from frappe import _, msgprint, is_whitelisted
from erpnext.stock.doctype.stock_reconciliation.stock_reconciliation import StockReconciliation
from frappe.model.docstatus import DocStatus
from metactical.custom_scripts.utils.metactical_utils import queue_action
from metactical.metactical.doctype.item_inventory_output.item_inventory_output import update_item_inventory_output

class CustomStockReconciliation(StockReconciliation):
	# def save(self):
	# 	if self.docstatus == DocStatus.submitted() and len(self.items) > 100 and \
	# 		self.ais_queue_status and self.ais_queue_status != "Queued":
	# 		msgprint(
	# 			_(
	# 				"The task has been enqueued as a background job. In case there is \
	# 				any issue on processing in background, the system will add a comment \
	# 				about the error on this document and revert to the Draft stage"
	# 			)
	# 		)
	# 		queue_action(self, "submit", timeout=2000)
	# 	else:
			# super().save()
   
	def on_submit(self):
		super(CustomStockReconciliation, self).on_submit()
		
		# Metactical Customization: Added
		for item in self.items:
			frappe.enqueue(update_item_inventory_output, item_code=item.item_code, queue='default')
