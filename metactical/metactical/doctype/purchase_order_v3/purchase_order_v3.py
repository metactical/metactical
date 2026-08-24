# Copyright (c) 2026, Storebuilder Commerce Inc and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from metactical.procurement_v3.utils import (
	F,
	mirror_po3_status,
	v3_may_close_native,
	v3_open_bo,
)


class PurchaseOrderV3(Document):
	def before_insert(self):
		shared_series_naming(self)

	def validate(self):
		validate(self)

	def on_submit(self):
		auto_send_on_approve(self)

	def on_update_after_submit(self):
		submitted_updates(self)

	def before_cancel(self):
		cancel_guard(self)

	def on_cancel(self):
		cancel_native_po(self)


# ---------------------------------------------------------------------------
# Migrated from Server Script "PO3 Shared Series Naming"
# (DocType Event / Before Insert on Purchase Order V3).
#
# Creates the native Purchase Order twin first, then names this PO3 after it so
# the pair share one number. before_insert runs immediately before set_new_name,
# so setting flags.name_set here suppresses the PO3-.YYYY.-.##### autoname.
# ---------------------------------------------------------------------------
def shared_series_naming(doc):
	if not (doc.name and doc.name.startswith("PO3-")):
		npo = frappe.new_doc("Purchase Order")
		npo.supplier = doc.supplier
		npo.company = doc.company
		npo.transaction_date = doc.order_date or frappe.utils.nowdate()
		npo.schedule_date = doc.required_by
		npo.currency = doc.currency
		npo.conversion_rate = F(doc.conversion_rate) or 1
		npo.buying_price_list = doc.buying_price_list
		npo.set_warehouse = doc.set_warehouse
		for d in doc.items:
			r = npo.append("items", {})
			r.item_code = d.item_code
			r.qty = F(d.qty) or 1
			r.rate = F(d.rate)
			r.schedule_date = d.required_by or doc.required_by
			r.warehouse = d.warehouse or doc.set_warehouse
		npo.insert(ignore_permissions=True)
		doc.name = "PO3-" + npo.name
		doc.flags.name_set = True
		doc.erp_purchase_order = npo.name
		frappe.db.set_value("Purchase Order", npo.name, "custom_purchase_order_v3", doc.name)


# ---------------------------------------------------------------------------
# Migrated from Server Script "PO3 Validate"
# (DocType Event / Before Save on Purchase Order V3).
#
# Resolves currency / price list / FX, recomputes the line amounts and header
# totals, derives the approval tier, fills the supplier contact + ship-to
# defaults, and mirrors the workflow state onto the native PO twin.
# ---------------------------------------------------------------------------
def mirror_status_now(erp_po, state):
	# Before Save: the new state is only on the in-memory doc, not yet in the DB
	if erp_po:
		frappe.db.set_value("Purchase Order", erp_po,
			"custom_po3_status", state, update_modified=False)


def validate(doc):
	company_currency = frappe.db.get_value("Company", doc.company, "default_currency")

	# On new docs Frappe pre-fills Buying Settings' default price list and the
	# company currency BEFORE validate runs - do not mistake those for a user's
	# choice. The supplier's own defaults win; no supplier default = leave blank
	# so the mandatory check forces a manual pick.
	if doc.is_new() and doc.supplier:
		sup = frappe.db.get_value("Supplier", doc.supplier,
			["default_price_list", "default_currency"], as_dict=True) or {}
		global_pl = frappe.db.get_single_value("Buying Settings", "buying_price_list")
		if not doc.buying_price_list or doc.buying_price_list == global_pl:
			doc.buying_price_list = sup.default_price_list
		if sup.default_currency and (not doc.currency or doc.currency == company_currency):
			doc.currency = sup.default_currency
	if not doc.currency:
		doc.currency = company_currency
	if doc.currency and doc.currency != company_currency and F(doc.conversion_rate) in (0.0, 1.0):
		rate = frappe.db.get_value("Currency Exchange",
			{"from_currency": doc.currency, "to_currency": company_currency},
			"exchange_rate", order_by="date desc")
		if not rate:
			try:
				rate = frappe.call("erpnext.setup.utils.get_exchange_rate",
					from_currency=doc.currency, to_currency=company_currency)
			except Exception:
				rate = None
		if rate:
			doc.conversion_rate = rate
	if F(doc.conversion_rate) == 0:
		doc.conversion_rate = 1

	total_qty = 0.0
	total = 0.0
	for d in doc.items:
		if F(d.rate) == 0 and doc.buying_price_list and d.item_code:
			price = frappe.db.get_value("Item Price",
				{"item_code": d.item_code, "price_list": doc.buying_price_list, "buying": 1},
				"price_list_rate", order_by="valid_from desc")
			if price:
				d.rate = price
		d.amount = F(d.qty) * F(d.rate)
		total_qty += F(d.qty)
		total += d.amount
		if not d.warehouse:
			d.warehouse = doc.set_warehouse
		if not d.required_by:
			d.required_by = doc.required_by
		if d.item_code and d.variant_of and not d.variant_attributes:
			attrs = frappe.get_all("Item Variant Attribute", filters={"parent": d.item_code},
				fields=["attribute", "attribute_value"], order_by="idx")
			d.variant_attributes = ", ".join([(a.attribute + ": " + (a.attribute_value or "")) for a in attrs])

	doc.total_qty = total_qty
	doc.total = total
	doc.base_grand_total = total * (F(doc.conversion_rate) or 1.0)

	if doc.base_grand_total >= 50000:
		doc.approval_tier = "L3 (Abdul) - over 50k"
	elif doc.base_grand_total >= 10000:
		doc.approval_tier = "Manager - 10k to 50k"
	else:
		doc.approval_tier = "Buyer - under 10k"

	if doc.is_new():
		if not doc.supplier_email:
			doc.supplier_email = frappe.db.get_value("Supplier", doc.supplier, "po3_order_email")
		if not doc.cc_email:
			doc.cc_email = frappe.db.get_value("Supplier", doc.supplier, "po3_cc_email")
		if not doc.po_print_format:
			doc.po_print_format = frappe.db.get_value("Supplier", doc.supplier, "po3_print_format")

	doc.bcc_email = frappe.db.get_single_value("Procurement Settings V3", "bcc_email")

	if doc.set_warehouse:
		w = frappe.db.get_value("Warehouse", doc.set_warehouse,
			["warehouse_name", "address_line_1", "address_line_2", "city", "state", "pin"], as_dict=True)
		if w:
			parts = [w.warehouse_name, w.address_line_1, w.address_line_2, w.city, w.state, w.pin]
			doc.ship_to_display = ", ".join([p for p in parts if p])

	if not doc.ack_expected:
		doc.confirmation_status = "Not Requested"
	elif doc.confirmation_status == "Not Requested":
		doc.confirmation_status = "Awaiting"

	mirror_status_now(doc.erp_purchase_order, doc.workflow_state or "Draft")


# ---------------------------------------------------------------------------
# Migrated from Server Script "PO3 Auto Send On Approve"
# (DocType Event / After Submit on Purchase Order V3).
#
# On approval: syncs the final lines onto the native PO twin and submits it
# (gated by Procurement Settings V3.posting_enabled), then emails the order to
# the supplier and flips the state to Sent to Supplier when that succeeds.
# ---------------------------------------------------------------------------
def auto_send_on_approve(doc):
	posting = frappe.db.get_single_value("Procurement Settings V3", "posting_enabled")

	# The native twin already exists (created with this PO3). Approval syncs the
	# final lines onto it and submits it.
	if doc.workflow_state == "Approved" and posting and doc.erp_purchase_order:
		if frappe.db.get_value("Purchase Order", doc.erp_purchase_order, "docstatus") == 0:
			npo = frappe.get_doc("Purchase Order", doc.erp_purchase_order)
			npo.supplier = doc.supplier
			npo.transaction_date = doc.order_date
			npo.schedule_date = doc.required_by
			npo.currency = doc.currency
			npo.conversion_rate = F(doc.conversion_rate) or 1
			npo.buying_price_list = doc.buying_price_list
			npo.set_warehouse = doc.set_warehouse
			npo.custom_purchase_order_v3 = doc.name
			if doc.notes_to_supplier:
				npo.notes = doc.notes_to_supplier
			npo.items = []
			for d in doc.items:
				if d.line_status == "Cancelled":
					continue
				r = npo.append("items", {})
				r.item_code = d.item_code
				r.qty = F(d.qty)
				r.rate = F(d.rate)
				r.schedule_date = d.required_by or doc.required_by
				r.warehouse = d.warehouse or doc.set_warehouse
			npo.flags.ignore_permissions = True
			npo.save()
			submitted = False
			err = ""
			try:
				npo.reload()
				npo.submit()
				submitted = True
			except Exception as e:
				err = str(e)[:180]
			if not submitted:
				try:
					npo.reload()
					npo.reload()
					npo.submit()
					submitted = True
				except Exception as e:
					err = str(e)[:180]
			npo.reload()
			for i in range(len(doc.items)):
				if i < len(npo.items):
					frappe.db.set_value("Purchase Order V3 Item", doc.items[i].name,
						{"erp_po_item": npo.items[i].name})
			frappe.db.set_value(doc.doctype, doc.name, {
				"posted_on": frappe.utils.now_datetime(),
				"posted_by": frappe.session.user})
			frappe.db.set_value(doc.doctype, doc.name, "post_error", None if submitted else err)
			if not submitted:
				frappe.msgprint("<b>Native PO " + npo.name + " was NOT submitted.</b><br>"
					+ err + "<br><br>Fix the cause, then use <b>Retry Native PO</b> on this order.")

	if doc.workflow_state == "Approved" and doc.supplier_email:
		pdf = None
		try:
			pdf = frappe.attach_print(doc.doctype, doc.name, print_format=doc.po_print_format or None, doc=doc)
		except Exception:
			pdf = None
		ok = False
		try:
			frappe.sendmail(
				recipients=[doc.supplier_email],
				cc=[doc.cc_email] if doc.cc_email else None,
				bcc=[doc.bcc_email] if doc.bcc_email else None,
				subject="Purchase Order " + (doc.erp_purchase_order or doc.name) + " - " + (doc.company or ""),
				message="Please find attached purchase order " + (doc.erp_purchase_order or doc.name)
					+ ".<br>Ship to: " + (doc.ship_to_display or "")
					+ (("<br><br>" + doc.notes_to_supplier) if doc.notes_to_supplier else "")
					+ "<br><br>Please reply with your order confirmation.",
				attachments=[pdf] if pdf else None,
				reference_doctype=doc.doctype, reference_name=doc.name)
			ok = True
		except Exception:
			ok = False
		if ok:
			frappe.db.set_value(doc.doctype, doc.name, {
				"workflow_state": "Sent to Supplier",
				"send_status": "Auto-Sent",
				"sent_on": frappe.utils.now_datetime(),
				"sent_by": frappe.session.user,
				"sent_method": "Email"})
		else:
			frappe.db.set_value(doc.doctype, doc.name, {"send_status": "Failed"})

	mirror_po3_status(doc.name)


# ---------------------------------------------------------------------------
# Migrated from Server Script "PO3 Submitted Updates"
# (DocType Event / After Save (Submitted Document) on Purchase Order V3).
#
# Runs on every save of an already-submitted order: self-heals a native twin
# that never submitted, stamps the manual send, applies backorder cancellations,
# handles a deliberate reopen, auto-closes once every line is terminal, and
# keeps the native PO's open/closed status in step.
# ---------------------------------------------------------------------------
def submitted_updates(doc):
	posting = frappe.db.get_single_value("Procurement Settings V3", "posting_enabled")

	# Self-heal: an approved PO3 whose twin is still a draft gets synced + submitted.
	if posting and doc.erp_purchase_order and doc.workflow_state in ("Approved", "Sent to Supplier", "Acknowledged", "Partially Received"):
		if frappe.db.get_value("Purchase Order", doc.erp_purchase_order, "docstatus") == 0:
			npo = frappe.get_doc("Purchase Order", doc.erp_purchase_order)
			npo.supplier = doc.supplier
			npo.transaction_date = doc.order_date
			npo.schedule_date = doc.required_by
			npo.currency = doc.currency
			npo.conversion_rate = F(doc.conversion_rate) or 1
			npo.buying_price_list = doc.buying_price_list
			npo.set_warehouse = doc.set_warehouse
			npo.custom_purchase_order_v3 = doc.name
			if doc.notes_to_supplier:
				npo.notes = doc.notes_to_supplier
			npo.items = []
			for d in doc.items:
				if d.line_status == "Cancelled":
					continue
				r = npo.append("items", {})
				r.item_code = d.item_code
				r.qty = F(d.qty)
				r.rate = F(d.rate)
				r.schedule_date = d.required_by or doc.required_by
				r.warehouse = d.warehouse or doc.set_warehouse
			npo.flags.ignore_permissions = True
			npo.save()
			submitted = False
			err = ""
			try:
				npo.reload()
				npo.submit()
				submitted = True
			except Exception as e:
				err = str(e)[:180]
			if not submitted:
				try:
					npo.reload()
					npo.reload()
					npo.submit()
					submitted = True
				except Exception as e:
					err = str(e)[:180]
			npo.reload()
			for i in range(len(doc.items)):
				if i < len(npo.items):
					frappe.db.set_value("Purchase Order V3 Item", doc.items[i].name,
						{"erp_po_item": npo.items[i].name})
			frappe.db.set_value(doc.doctype, doc.name, {
				"posted_on": frappe.utils.now_datetime(),
				"posted_by": frappe.session.user})
			frappe.db.set_value(doc.doctype, doc.name, "post_error", None if submitted else err)
			if not submitted:
				frappe.msgprint("<b>Native PO " + npo.name + " was NOT submitted.</b><br>"
					+ err + "<br><br>Fix the cause, then use <b>Retry Native PO</b> on this order.")

	if doc.workflow_state == "Sent to Supplier" and not doc.sent_on:
		frappe.db.set_value(doc.doctype, doc.name, {
			"sent_on": frappe.utils.now_datetime(),
			"sent_by": frappe.session.user,
			"send_status": "Manually Sent" if doc.send_status in ("Not Sent", "Failed") else doc.send_status,
			"sent_method": doc.sent_method or "Other"})

	for d in doc.items:
		if d.backorder_status == "Cancelled" and d.line_status == "Back-ordered":
			if not d.backorder_cancel_reason:
				frappe.throw("Row " + str(d.idx) + ": pick a Backorder Cancel Reason before cancelling the backorder.")
			new_status = "Closed Short" if F(d.received_qty) > 0 else "Cancelled"
			frappe.db.set_value("Purchase Order V3 Item", d.name, {
				"line_status": new_status,
				"short_qty": F(d.qty) - F(d.received_qty)})


	# ---- a deliberate reopen ----------------------------------------
	# Header says the order is live again while every line is still terminal:
	# that only happens right after someone reopens it. Put the short-closed
	# lines back so there is something outstanding, and remember we did.
	if doc.workflow_state in ("Sent to Supplier", "Acknowledged",
			"Partially Received", "Received"):
		term_all = True
		shorts = []
		for r in frappe.get_all("Purchase Order V3 Item", filters={"parent": doc.name},
				fields=["name", "line_status"], limit_page_length=0):
			if r.line_status not in ("Received", "Closed Short", "Cancelled",
					"Supplier Stock Out", "Discontinued"):
				term_all = False
			if r.line_status == "Closed Short":
				shorts.append(r.name)
		if term_all:
			frappe.db.set_value("Purchase Order V3", doc.name,
				"manually_reopened", 1, update_modified=False)
			for nm in shorts:
				frappe.db.set_value("Purchase Order V3 Item", nm,
					{"line_status": "Open", "short_qty": 0})
			if shorts:
				frappe.msgprint("Reopened - " + str(len(shorts))
					+ " short-closed line(s) put back to Open, so the balance is "
					+ "expected again.")
	elif doc.workflow_state in ("Closed", "Closed Short"):
		frappe.db.set_value("Purchase Order V3", doc.name,
			"manually_reopened", 0, update_modified=False)

	open_bo_now = v3_open_bo(doc.name)
	rows = frappe.get_all("Purchase Order V3 Item", filters={"parent": doc.name},
		fields=["name", "line_status"])
	all_terminal = bool(rows)
	any_short = False
	for r in rows:
		if r.line_status not in ("Received", "Closed Short", "Cancelled", "Supplier Stock Out", "Discontinued"):
			all_terminal = False
		elif r.name in open_bo_now:
			# goods are still owed on this line - nothing here is finished
			all_terminal = False
		if r.line_status in ("Closed Short", "Cancelled", "Supplier Stock Out", "Discontinued"):
			any_short = True
	reopened_flag = frappe.db.get_value("Purchase Order V3", doc.name, "manually_reopened")
	if (all_terminal and not reopened_flag and doc.workflow_state in
			("Sent to Supplier", "Acknowledged", "Partially Received", "Received")):
		frappe.db.set_value(doc.doctype, doc.name, {
			"workflow_state": "Closed Short" if any_short else "Closed",
			"receipt_status": "Closed Short" if any_short else "Received"})
		open_grs = frappe.get_all("Goods Receipt V3",
			filters={"purchase_order_v3": doc.name, "docstatus": 0},
			fields=["name"], limit_page_length=1)
		if any_short and doc.erp_purchase_order and not open_grs:
			try:
				frappe.get_doc("Purchase Order", doc.erp_purchase_order).update_status("Closed")
			except Exception:
				frappe.db.set_value("Purchase Order", doc.erp_purchase_order, "status", "Closed")

	mirror_po3_status(doc.name)

	# ---- native PO follows the PO3 closing state --------------------
	# Closing by hand used to change nothing outside V3: the native close only
	# ran from the receipt path, or when every line happened to be terminal.
	if doc.erp_purchase_order:
		native_now = frappe.db.get_value("Purchase Order", doc.erp_purchase_order, "status")
		drafts = frappe.get_all("Goods Receipt V3",
			filters={"purchase_order_v3": doc.name, "docstatus": 0},
			fields=["name"], limit_page_length=1)
		# "Closed" is fully received - ERPNext shows that as To Bill and needs it
		# left open to be invoiced. Only giving up on a balance justifies a close.
		if doc.workflow_state == "Closed Short":
			gate = v3_may_close_native(doc.erp_purchase_order)
			if gate["ok"] and not drafts:
				try:
					frappe.get_doc("Purchase Order", doc.erp_purchase_order).update_status("Closed")
				except Exception:
					frappe.db.set_value("Purchase Order", doc.erp_purchase_order,
						"status", "Closed")
				frappe.msgprint("Native PO " + doc.erp_purchase_order + " closed to match.")
			elif gate["why"]:
				frappe.msgprint(gate["why"])
			elif drafts:
				frappe.msgprint("Native PO " + doc.erp_purchase_order
					+ " left open - there is still a draft Goods Receipt against this order.")
		elif doc.workflow_state in ("Sent to Supplier", "Acknowledged",
				"Partially Received", "Received") and native_now == "Closed":
			try:
				frappe.get_doc("Purchase Order", doc.erp_purchase_order).update_status("Submitted")
			except Exception:
				frappe.db.set_value("Purchase Order", doc.erp_purchase_order,
					"status", "To Receive and Bill")
			frappe.msgprint("Native PO " + doc.erp_purchase_order + " reopened to match.")


# ---------------------------------------------------------------------------
# Migrated from Server Script "PO3 Cancel Guard"
# (DocType Event / Before Cancel on Purchase Order V3).
#
# Refuses to cancel an order that still has live confirmations, shipments,
# receipts or claims against it, or that has already taken stock in, and points
# the user at Close Short instead.
# ---------------------------------------------------------------------------
def cancel_guard(doc):
	blockers = []

	for s in frappe.get_all("Supplier Order Confirmation V3",
			filters={"purchase_order_v3": doc.name, "docstatus": ("<", 2)},
			fields=["name", "workflow_state", "docstatus"], limit_page_length=0):
		what = "confirmation " + s.name + " (" + str(s.workflow_state) + ")"
		if s.docstatus == 0:
			blockers.append(what + " - delete it, or cancel it first")
		else:
			blockers.append(what + " - cancel the confirmation first")

	for s in frappe.get_all("Inbound Shipment V3",
			filters={"purchase_order_v3": doc.name, "docstatus": ("<", 2)},
			fields=["name", "workflow_state"], limit_page_length=0):
		blockers.append("shipment " + s.name + " (" + str(s.workflow_state)
			+ ") - goods are on the way; cancel or delete the shipment first")

	for s in frappe.get_all("Goods Receipt V3",
			filters={"purchase_order_v3": doc.name, "docstatus": ("<", 2)},
			fields=["name", "workflow_state"], limit_page_length=0):
		blockers.append("receipt " + s.name + " (" + str(s.workflow_state)
			+ ") - cancel or delete the receipt first")

	for s in frappe.get_all("Supplier Claim V3",
			filters={"purchase_order_v3": doc.name, "docstatus": ("<", 2)},
			fields=["name"], limit_page_length=0):
		blockers.append("claim " + s.name + " - resolve or cancel the claim first")

	got = 0.0
	for d in doc.items:
		got = got + float(d.received_qty or 0)
	if got > 0:
		blockers.append("goods already received (" + str(got)
			+ " units) - a cancelled order cannot hold stock. Reverse the receipts, "
			+ "or use Close Short to stop the balance instead")

	if blockers:
		frappe.throw("<b>" + doc.name + " cannot be cancelled yet.</b><br><br>"
			+ "<br>".join(blockers)
			+ "<br><br>If the order is simply not going to be filled, "
			+ "<b>Close Short</b> ends it while keeping the history.")


# ---------------------------------------------------------------------------
# Migrated from Server Script "PO3 Cancel Native PO"
# (DocType Event / After Cancel on Purchase Order V3).
#
# Cancels the native twin when nothing was received against it; closes it
# instead when receipts exist, so no further stock can land on it.
# ---------------------------------------------------------------------------
def cancel_native_po(doc):
	# PO3 cancelled -> deal with the native twin. Cancel it when nothing was
	# received against it; otherwise close it so nothing further can be received.
	if doc.erp_purchase_order:
		npo = frappe.get_doc("Purchase Order", doc.erp_purchase_order)
		if npo.docstatus == 1:
			has_receipts = frappe.db.exists("Purchase Receipt Item",
				{"purchase_order": npo.name, "docstatus": 1})
			if not has_receipts:
				try:
					npo.cancel()
					frappe.msgprint("Native PO " + npo.name + " cancelled.")
				except Exception:
					frappe.db.set_value("Purchase Order", npo.name, "status", "Closed")
					frappe.msgprint("Native PO " + npo.name + " could not be cancelled - marked Closed instead.")
			else:
				try:
					npo.update_status("Closed")
				except Exception:
					frappe.db.set_value("Purchase Order", npo.name, "status", "Closed")
				frappe.msgprint("Native PO " + npo.name + " has receipts - marked Closed (no further receiving).")

	mirror_po3_status(doc.name)
