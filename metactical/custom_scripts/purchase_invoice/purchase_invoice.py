import frappe
from erpnext.accounts.doctype.purchase_invoice.purchase_invoice import PurchaseInvoice
from frappe.utils import flt, cstr, now, get_datetime_str, file_lock, date_diff, now_datetime
from frappe import _, msgprint, is_whitelisted
from metactical.custom_scripts.utils.metactical_utils import queue_action
from frappe.model.docstatus import DocStatus

class CustomPurchaseInvoice(PurchaseInvoice):
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
