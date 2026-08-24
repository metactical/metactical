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

	def on_cancel(self):
		# After Cancel: ERPNext unwinds the invoice first, then the V3 reaction
		# re-derives the native PO's open/closed state from what is left.
		super(CustomPurchaseInvoice, self).on_cancel()
		v3_cancel_reopen_po(self)

	def before_cancel(self):
		# V3 reaction runs BEFORE super(), matching the Server Script's
		# "Before Cancel" event: the native PO has to be reopened while the
		# invoice is still submitted, or ERPNext refuses the status change.
		v3_precancel_reopen_po(self)
		super(CustomPurchaseInvoice, self).before_cancel()

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


# ---------------------------------------------------------------------------
# Migrated from Server Script "Native PI Precancel Reopen PO"
# (DocType Event / Before Cancel on Purchase Invoice).
#
# Reopens a Closed native PO before the invoice is cancelled, because ERPNext
# will not let a Closed order have its billed amounts unwound.
# ---------------------------------------------------------------------------
def v3_precancel_reopen_po(doc):
	for d in doc.items:
		if not d.purchase_order:
			continue
		st = frappe.db.get_value("Purchase Order", d.purchase_order,
			["status", "docstatus"], as_dict=True)
		if not st or st.docstatus != 1 or st.status != "Closed":
			continue
		if not frappe.db.exists("Purchase Order V3", {"erp_purchase_order": d.purchase_order}):
			continue
		try:
			frappe.get_doc("Purchase Order", d.purchase_order).update_status("Submitted")
			frappe.msgprint("Purchase Order " + d.purchase_order
				+ " reopened so this invoice can be cancelled.")
		except Exception:
			pass


# ---------------------------------------------------------------------------
# Migrated from Server Script "Native PI Cancel Reopen PO"
# (DocType Event / After Cancel on Purchase Invoice).
#
# With the invoice gone there is received-but-unbilled value again, so a native
# PO that had been closed to match a Closed Short PO3 is reopened.
# ---------------------------------------------------------------------------
def v3_cancel_reopen_po(doc):
	seen = {}
	for d in doc.items:
		if d.purchase_order:
			seen[d.purchase_order] = 1
	for po_name in seen:
		st = frappe.db.get_value("Purchase Order", po_name,
			["status", "docstatus", "per_received", "per_billed"], as_dict=True)
		if not st or st.docstatus != 1 or st.status != "Closed":
			continue
		if float(st.per_received or 0) <= 0:
			continue
		if float(st.per_billed or 0) + 0.001 >= float(st.per_received or 0):
			continue
		if not frappe.db.exists("Purchase Order V3", {"erp_purchase_order": po_name}):
			continue
		try:
			frappe.get_doc("Purchase Order", po_name).update_status("Submitted")
			frappe.msgprint("Purchase Order " + po_name + " reopened - cancelling this "
				+ "invoice leaves received goods unbilled, and a Closed order cannot "
				+ "be invoiced.")
		except Exception:
			pass
