# Copyright (c) 2026, Storebuilder Commerce Inc and contributors
# For license information, please see license.txt

"""Shared helpers for the Procurement V3 flow.

Each function here was defined -- byte-identically -- at the top of several of
the old V3 Server Scripts. They are hoisted into one module during the move to
code so the duplicates collapse without any change in behaviour:

    F                    17 scripts
    mirror_po3_status     8 scripts
    v3_may_close_native   2 scripts
    v3_open_bo            2 scripts
    v3_reconcile          2 scripts  (see the warning on that function)
"""

import frappe


def F(x):
	return float(x or 0)


# ---------------------------------------------------------------------------
# The supplier SKU printed on an order line comes off the Item's Supplier Items
# table. Prefer the order's own supplier; when that has no entry (supplier not
# picked yet, or a sister account like "Carhartt - USA"), fall back to the
# item's default supplier and then to any part number the item carries, so a
# line never comes out blank while the Item itself has one.
# ---------------------------------------------------------------------------
def item_supplier_part_no(item_code, supplier=None):
	rows = frappe.get_all("Item Supplier",
		filters={"parent": item_code, "parenttype": "Item", "supplier_part_no": ("is", "set")},
		fields=["supplier", "supplier_part_no"], order_by="idx asc")
	if not rows:
		return None
	by_supplier = {r.supplier: r.supplier_part_no for r in rows}
	if supplier and by_supplier.get(supplier):
		return by_supplier[supplier]
	for d in frappe.get_all("Item Default", filters={"parent": item_code, "parenttype": "Item"},
			fields=["default_supplier"], order_by="idx asc"):
		if d.default_supplier and by_supplier.get(d.default_supplier):
			return by_supplier[d.default_supplier]
	return rows[0].supplier_part_no


def email_list(value):
	"""A CC / BCC field's addresses as a list. The fields hold them comma-separated
	(the form shows each as a pill); older values may use ; or new lines."""
	import re
	return [e for e in (x.strip() for x in re.split(r"[,;\n]+", value or "")) if e]


def clean_email_list(doc, fieldname):
	"""Validate every address in a CC / BCC field and store them tidied:
	comma-separated, duplicates dropped."""
	from frappe.utils import validate_email_address

	seen, bad = [], []
	for e in email_list(doc.get(fieldname)):
		if not validate_email_address(e):
			bad.append(e)
		elif e.lower() not in [x.lower() for x in seen]:
			seen.append(e)
	if bad:
		frappe.throw("{0}: not a valid email address: <b>{1}</b>".format(
			doc.meta.get_label(fieldname), ", ".join(bad)), frappe.InvalidEmailAddressError)
	doc.set(fieldname, ", ".join(seen) or None)


def require_email_signature(doc, fieldname):
	"""A Main Signature is optional, but a user picked for it must have an Email
	Signature: PO emails are signed with it, and an empty one would send them
	out unsigned without anyone noticing."""
	user = doc.get(fieldname)
	if not user:
		return
	full_name, signature = frappe.db.get_value("User", user, ["full_name", "email_signature"]) or (None, None)
	if not (signature or "").strip():
		frappe.throw("<b>{0}</b> has no Email Signature, so they can't be the {1}. Add one on their "
			"User record (Settings tab, Email section), or pick another user.".format(
				full_name or user, doc.meta.get_label(fieldname)), title="No email signature")


def validate_supplier_po_emails(doc):
	"""Run from Supplier's validate (custom_scripts/supplier/supplier.py): the
	PO V3 Ordering CC / BCC addresses and Main Signature."""
	for f in ("po3_cc_email", "nat_po3_bcc_email"):
		if doc.meta.has_field(f):
			clean_email_list(doc, f)
	if doc.meta.has_field("nat_po3_signature_user"):
		require_email_signature(doc, "nat_po3_signature_user")


def item_unavailable(item_code):
	"""Why an item may not go on a new order or receipt: "disabled",
	"discontinued" (Item.ifw_discontinued), or None when it may."""
	if not item_code:
		return None
	disabled, discontinued = frappe.get_cached_value("Item", item_code, ["disabled", "ifw_discontinued"]) or (0, 0)
	if frappe.utils.cint(disabled):
		return "disabled"
	if frappe.utils.cint(discontinued):
		return "discontinued"
	return None


def throw_unavailable(bad, action):
	"""bad: [(row idx, item_code, why)] -> one message listing every row.
	action: what the items can't be, e.g. "ordered"."""
	if bad:
		frappe.throw("These items are discontinued or disabled and can't be {0}:<br>".format(action)
			+ "<br>".join("Row {0}: <b>{1}</b> ({2})".format(idx, code, why) for idx, code, why in bad),
			title="Item not available")


def billable_qty(qty, short_qty, over_qty=0):
	"""How much of a line is still expected to cost us.

	short_qty is the quantity that will never arrive, and every part of the flow
	already maintains it with exactly that meaning: the confirmation sets it to
	the whole line on Supplier Stock Out / Discontinued / Cancelled and to the
	unconfirmed remainder on a partial, and a receipt sets it to the shortfall
	only when it short-closes the line. A balance that is merely late -- a
	back-order, or a partial receipt still expecting the rest -- leaves it at 0.

	So the ordered quantity minus that is what the order is still worth, and no
	status list has to be kept in step here to work it out. over_qty is the
	other way round: received beyond the order (a receipt sets it), and kept --
	the order is worth what actually arrived, as the native PO and its receipt
	are.
	"""
	return max(F(qty) - F(short_qty) + F(over_qty), 0.0)


def v3_recalc_totals(po3_name):
	"""Re-derive a submitted order's totals from its lines.

	The header totals are worked out in the PO3 controller's validate, which
	stops running the moment the order is submitted -- and lines go dead well
	after that, when the supplier answers. Without this, an order that lost half
	its lines to a stock-out kept quoting the full price it was placed at.

	approval_tier is deliberately left alone. It records the authority the order
	needed when it was placed, which is a fact about the past; a later stock-out
	does not retroactively make it a smaller decision.
	"""
	from metactical.metactical.doctype.supplier_order_confirmation_v3.supplier_order_confirmation_v3 \
		import open_backorder_qty
	from metactical.procurement_v3.taxes import save_v3_totals, set_v3_totals

	doc = frappe.get_doc("Purchase Order V3", po3_name)
	# a back-ordered balance is not part of the order's value until it arrives
	backordered = open_backorder_qty(po3_name)
	total_qty = 0.0
	lines, rows = [], []
	for r in doc.items:
		qty = max(billable_qty(r.qty, r.short_qty, r.over_qty) - backordered.get(r.name, 0), 0)
		amount = qty * F(r.rate)
		if F(r.amount) != amount or F(r.expected_qty) != qty:
			# keep the grid adding up to the header - a column that does not sum
			# to the total printed under it is the thing people query. Qty stays
			# what was ordered (short_qty and the back-orders are measured from
			# it); expected_qty is what the line comes to now, as on the native PO
			frappe.db.set_value("Purchase Order V3 Item", r.name,
				{"amount": amount, "expected_qty": qty}, update_modified=False)
		total_qty += qty
		if r.item_code:
			lines.append((r.item_code, qty, r.rate))
			rows.append(r)

	# taxes on a smaller order are smaller too: work them out again with the
	# grand totals (procurement_v3/taxes.py)
	set_v3_totals(doc, lines, rows)
	frappe.db.set_value("Purchase Order V3", po3_name, "total_qty", total_qty, update_modified=False)
	save_v3_totals(doc, rows)


def mirror_po3_status(po3_name):
	row = frappe.db.get_value("Purchase Order V3", po3_name,
		["erp_purchase_order", "workflow_state"], as_dict=True)
	if row and row.erp_purchase_order:
		frappe.db.set_value("Purchase Order", row.erp_purchase_order,
			"custom_po3_status", row.workflow_state, update_modified=False)


def v3_may_close_native(po_name):
	st = frappe.db.get_value("Purchase Order", po_name,
		["status", "docstatus", "per_received", "per_billed"], as_dict=True)
	if not st or st.docstatus != 1:
		return {"ok": 0, "why": ""}
	if st.status in ("Closed", "Cancelled"):
		return {"ok": 0, "why": ""}
	if float(st.per_received or 0) <= 0:
		return {"ok": 1, "why": ""}          # nothing arrived, nothing to bill
	# per_billed is measured against ORDERED value, so a short-closed order
	# never reaches 100%. What matters is that everything which ARRIVED has
	# been invoiced.
	if float(st.per_billed or 0) + 0.001 >= float(st.per_received or 0):
		return {"ok": 1, "why": ""}
	return {"ok": 0, "why": "Native PO " + po_name + " left open: "
		+ str(round(float(st.per_received or 0), 1)) + "% received but only "
		+ str(round(float(st.per_billed or 0), 1)) + "% billed. ERPNext blocks a "
		+ "Purchase Invoice against a Closed order, so it must stay open until "
		+ "the supplier's invoice is posted."}


def v3_open_bo(po3_name):
	open_items = {}
	soc = frappe.db.get_value("Supplier Order Confirmation V3",
		{"purchase_order_v3": po3_name, "docstatus": ("<", 2)}, "name")
	if not soc:
		return open_items
	for b in frappe.get_all("Supplier Order Confirmation V3 Backorder",
			filters={"parent": soc}, fields=["po3_item", "status"], limit_page_length=0):
		if b.po3_item and b.status not in ("Received", "Cancelled"):
			open_items[b.po3_item] = 1
	return open_items


# NOTE: the "V3 Reconcile Receiving" API script defines its own v3_reconcile
# with a DIFFERENT body. That one is not interchangeable with this and stays
# local to the API module -- do not collapse the two.

def v3_reconcile(po3_name):
	# --- confirmation back-order rows ---
	soc = frappe.db.get_value("Supplier Order Confirmation V3",
		{"purchase_order_v3": po3_name, "docstatus": ("<", 2)}, "name")
	if soc:
		for b in frappe.get_all("Supplier Order Confirmation V3 Backorder",
				filters={"parent": soc}, fields=["name", "po3_item", "status"]):
			line = frappe.db.get_value("Purchase Order V3 Item", b.po3_item,
				["received_qty", "qty"], as_dict=True)
			if not line:
				continue
			got = float(line.received_qty or 0)
			upd = {"received_qty": got}
			if b.status in ("Open", "Shipped") and got >= float(line.qty or 0):
				upd["status"] = "Received"
			frappe.db.set_value("Supplier Order Confirmation V3 Backorder", b.name, upd)

	# --- shipments: flag what has landed, close any left In Transit ---
	for ins in frappe.get_all("Inbound Shipment V3",
			filters={"purchase_order_v3": po3_name, "docstatus": ("<", 2)},
			fields=["name", "workflow_state", "docstatus"]):
		d = frappe.get_doc("Inbound Shipment V3", ins.name)
		all_landed = True if d.items else False
		for it in d.items:
			if not it.po3_item:
				all_landed = False
				continue
			line = frappe.db.get_value("Purchase Order V3 Item", it.po3_item,
				["received_qty", "qty"], as_dict=True)
			if line and float(line.received_qty or 0) >= float(line.qty or 0):
				frappe.db.set_value("Inbound Shipment V3 Item", it.name, "received_flag", 1)
			else:
				all_landed = False
		if not all_landed:
			continue
		for b in d.boxes:
			frappe.db.set_value("Inbound Shipment V3 Box", b.name, "received", 1)
		if ins.docstatus == 0 and ins.workflow_state in ("Draft", "In Transit"):
			try:
				d.reload()
				d.workflow_state = "Received"
				d.docstatus = 1
				d.save()
				frappe.msgprint("Inbound Shipment " + ins.name
					+ " was still " + (ins.workflow_state or "Draft")
					+ " - marked <b>Received</b>, since its goods have all been receipted.")
			except Exception:
				pass


def validate_rate_except_v3(doc, ref_details, v3_rows, link_field):
	"""ERPNext's "Maintain Same Rate" check, minus the rows a Purchase Receipt V3
	posted. Those carry the supplier's confirmed rate (SOC3), which the PO --
	the record of what was ordered -- never takes, so they may differ from it.
	Their link to the PO line is hidden only while the check runs."""
	from erpnext.utilities.transaction_base import TransactionBase

	hidden = [(d, d.get(link_field)) for d in v3_rows if d.get(link_field)]
	for d, _ in hidden:
		d.set(link_field, None)
	try:
		TransactionBase.validate_rate_with_reference_doc(doc, ref_details)
	finally:
		for d, value in hidden:
			d.set(link_field, value)
