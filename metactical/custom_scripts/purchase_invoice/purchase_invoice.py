import frappe
from erpnext.accounts.doctype.purchase_invoice.purchase_invoice import PurchaseInvoice
from frappe.utils import flt, cstr, now, get_datetime_str, file_lock, date_diff, now_datetime
from frappe import _, msgprint, is_whitelisted
from metactical.custom_scripts.utils.metactical_utils import queue_action
from frappe.model.docstatus import DocStatus

class CustomPurchaseInvoice(PurchaseInvoice):
	def on_submit(self):
		super(CustomPurchaseInvoice, self).on_submit()
		v3_close_short_closed_po(self)

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


# ---------------------------------------------------------------------------
# Migrated from Server Script "Native PI Close Short Closed PO"
# (DocType Event / After Submit on Purchase Invoice).
#
# Once everything that actually arrived has been invoiced, a PO3 sitting at
# Closed Short can have its native PO closed too, so the unfilled balance stops
# counting as on order.
# ---------------------------------------------------------------------------
def v3_close_short_closed_po(doc):
	seen = {}
	for d in doc.items:
		if d.purchase_order:
			seen[d.purchase_order] = 1
	for po_name in seen:
		p3 = frappe.db.get_value("Purchase Order V3", {"erp_purchase_order": po_name},
			["name", "workflow_state"], as_dict=True)
		if not p3 or p3.workflow_state != "Closed Short":
			continue
		st = frappe.db.get_value("Purchase Order", po_name,
			["status", "docstatus", "per_received", "per_billed"], as_dict=True)
		if not st or st.docstatus != 1 or st.status in ("Closed", "Cancelled"):
			continue
		if float(st.per_billed or 0) + 0.001 < float(st.per_received or 0):
			continue                     # still something received but unbilled
		drafts = frappe.get_all("Goods Receipt V3",
			filters={"purchase_order_v3": p3.name, "docstatus": 0},
			fields=["name"], limit_page_length=1)
		if drafts:
			continue
		try:
			frappe.get_doc("Purchase Order", po_name).update_status("Closed")
		except Exception:
			frappe.db.set_value("Purchase Order", po_name, "status", "Closed")
		frappe.msgprint("Purchase Order " + po_name + " is now fully invoiced for what "
			+ "arrived, and " + p3.name + " is Closed Short - closing it so the "
			+ "unfilled balance stops counting as on order.")
