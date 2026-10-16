"""
Create a Purchase Receipt from either a Supplier Order Confirmation or an
Inbound Shipment.

Entry points (all whitelisted):

  make_purchase_receipt_from_confirmation(soc_name)
      Simple path — no box detail needed. Uses confirmed_qty capped at
      outstanding PO qty.

  make_purchase_receipt_from_shipment(ins_name, box_no=None)
      Per-shipment or per-box path. Pass box_no to receive a single carton.
      Omit box_no to receive the whole shipment.

On PR submit the caller should call mark_source_lines_received() to flip
received_flag on the consumed source rows/boxes.
"""

import frappe
from frappe import _
from frappe.utils import flt


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

@frappe.whitelist()
def make_purchase_receipt_from_confirmation(soc_name):
	"""Create a Draft PR from a Supplier Order Confirmation (simple path)."""
	soc = frappe.get_doc("Supplier Order Confirmation", soc_name)
	if soc.docstatus != 1:
		frappe.throw(_("Supplier Order Confirmation {0} must be submitted before creating a Purchase Receipt.").format(soc_name))

	lines = [
		line for line in soc.items
		if not line.received_flag
		and line.confirmed_qty > 0
		and line.line_status not in ("Out of Stock", "Discontinued")
	]
	if not lines:
		frappe.throw(_("No unreceived lines available on {0}.").format(soc_name))

	po = frappe.get_doc("Purchase Order", soc.purchase_order)
	outstanding = _outstanding_qty_map(po)

	pr_items = []
	for line in lines:
		qty = min(flt(line.confirmed_qty), flt(outstanding.get(line.po_detail, 0)))
		if qty <= 0:
			continue
		pr_items.append(_build_pr_item(
			po_row=_po_row(po, line.po_detail),
			qty=qty,
			source_doctype="Supplier Order Confirmation",
			source_name=soc_name,
			source_detail=line.name,
			box_no=None,
		))

	if not pr_items:
		frappe.throw(_("All lines on {0} are already fully received or have zero outstanding qty.").format(soc_name))

	return _build_pr(po, pr_items)


@frappe.whitelist()
def make_purchase_receipt_from_shipment(ins_name, box_no=None):
	"""Create a Draft PR from an Inbound Shipment (per-box or whole shipment)."""
	ins = frappe.get_doc("Inbound Shipment", ins_name)
	if ins.docstatus != 1:
		frappe.throw(_("Inbound Shipment {0} must be submitted before creating a Purchase Receipt.").format(ins_name))

	lines = [
		line for line in ins.items
		if not line.received_flag
		and line.shipped_qty > 0
		and (box_no is None or line.box_no == box_no)
	]
	if not lines:
		msg = _("No unreceived lines for box {0} on {1}.").format(box_no, ins_name) if box_no \
			else _("No unreceived lines on {0}.").format(ins_name)
		frappe.throw(msg)

	po = frappe.get_doc("Purchase Order", ins.purchase_order)
	outstanding = _outstanding_qty_map(po)

	pr_items = []
	for line in lines:
		qty = min(flt(line.shipped_qty), flt(outstanding.get(line.po_detail, 0)))
		if qty <= 0:
			continue
		pr_items.append(_build_pr_item(
			po_row=_po_row(po, line.po_detail),
			qty=qty,
			source_doctype="Inbound Shipment",
			source_name=ins_name,
			source_detail=line.name,
			box_no=line.box_no,
		))

	if not pr_items:
		frappe.throw(_("All selected lines are already fully received or have zero outstanding qty."))

	return _build_pr(po, pr_items)


@frappe.whitelist()
def mark_source_lines_received(pr_name):
	"""Manual/API entry point: flip received_flag for an already-submitted PR."""
	pr = frappe.get_doc("Purchase Receipt", pr_name)
	if pr.docstatus != 1:
		frappe.throw(_("Purchase Receipt must be submitted first."))
	_mark_source_lines_received(pr)
	frappe.db.commit()


def _mark_source_lines_received(pr):
	"""
	Flips received_flag on the source rows that fed this PR, and marks boxes
	received once all their lines are done. Called automatically from
	Purchase Receipt.on_submit (see CustomPurchaseReceipt) so double-receiving
	the same Confirmation/Shipment line is not possible.

	The PR items carry custom fields neb_source_doctype / neb_source_name /
	neb_source_detail written by the builder above.
	"""
	source_child_doctype = {
		"Supplier Order Confirmation": "Supplier Order Confirmation Item",
		"Inbound Shipment": "Inbound Shipment Item",
	}

	for item in pr.items:
		source_doctype = item.get("neb_source_doctype")
		source_detail  = item.get("neb_source_detail")
		if source_doctype and source_detail and source_doctype in source_child_doctype:
			frappe.db.set_value(source_child_doctype[source_doctype], source_detail, "received_flag", 1)

	# Mark boxes received if all their items are now flagged
	touched_shipments = {
		item.get("neb_source_name")
		for item in pr.items
		if item.get("neb_source_doctype") == "Inbound Shipment" and item.get("neb_source_name")
	}
	for ins_name in touched_shipments:
		ins = frappe.get_doc("Inbound Shipment", ins_name)
		for box in ins.boxes:
			box_items = [l for l in ins.items if l.box_no == box.box_no]
			if box_items and all(l.received_flag for l in box_items):
				frappe.db.set_value("Inbound Shipment Box", box.name, "received", 1)


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #

def _outstanding_qty_map(po):
	"""Return {po_item_row_name: outstanding_qty} from the PO."""
	return {
		row.name: flt(row.qty) - flt(row.received_qty)
		for row in po.items
	}


def _po_row(po, po_detail):
	for row in po.items:
		if row.name == po_detail:
			return row
	return None


def _build_pr_item(po_row, qty, source_doctype, source_name, source_detail, box_no):
	if not po_row:
		frappe.throw(_("Could not find PO line {0}").format(source_detail))
	return {
		"item_code":            po_row.item_code,
		"item_name":            po_row.item_name,
		"description":          po_row.description,
		"uom":                  po_row.uom,
		"stock_uom":            po_row.stock_uom,
		"conversion_factor":    po_row.conversion_factor,
		"qty":                  qty,
		"rate":                 po_row.rate,
		"purchase_order":       po_row.parent,
		"purchase_order_item":  po_row.name,    # critical — keeps billing/receipt status
		"warehouse":            po_row.warehouse,
		# Back-references for mark_source_lines_received
		"neb_source_doctype":   source_doctype,
		"neb_source_name":      source_name,
		"neb_source_detail":    source_detail,
		"neb_box_no":           box_no or "",
	}


def _build_pr(po, pr_items):
	pr = frappe.new_doc("Purchase Receipt")
	pr.supplier        = po.supplier
	pr.company         = po.company
	pr.purchase_order  = po.name
	pr.posting_date    = frappe.utils.today()
	pr.set("items", pr_items)
	pr.set_missing_values()
	pr.calculate_taxes_and_totals()
	return pr
