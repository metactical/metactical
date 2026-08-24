# Copyright (c) 2026, Storebuilder Commerce Inc and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from metactical.procurement_v3.utils import F, mirror_po3_status


class InboundShipmentV3(Document):
	def validate(self):
		validate(self)

	def after_insert(self):
		auto_in_transit(self)


# ---------------------------------------------------------------------------
# Migrated from Server Script "INS3 Validate"
# (DocType Event / Before Save on Inbound Shipment V3).
#
# Lays out what this shipment is carrying from the confirmation's promises less
# whatever is already in transit, warns on lines the supplier said were not
# coming and on over-shipment, totals the boxes, and validates the carrier /
# service pair and tracking link.
#
# track_url / check_service stay nested: they are defined mid-script in the
# original and read the enclosing scope.
# ---------------------------------------------------------------------------
def validate(doc):
	po = frappe.get_doc("Purchase Order V3", doc.purchase_order_v3)
	if po.docstatus != 1:
		frappe.throw("Purchase Order V3 " + po.name + " is not approved yet.")

	# there is exactly one confirmation per PO - attach it rather than asking
	if not doc.supplier_order_confirmation_v3:
		hit = frappe.get_all("Supplier Order Confirmation V3",
			filters={"purchase_order_v3": po.name, "docstatus": ("<", 2)},
			fields=["name"], order_by="creation desc", limit_page_length=1)
		if hit:
			doc.supplier_order_confirmation_v3 = hit[0].name

	# what the supplier actually committed to, per PO3 line
	promised = {}
	not_coming = {}
	if doc.supplier_order_confirmation_v3:
		for ln in frappe.get_all("Supplier Order Confirmation V3 Item",
				filters={"parent": doc.supplier_order_confirmation_v3},
				fields=["po3_item", "item_code", "confirmed_qty", "line_status"]):
			promised[ln.po3_item] = ln
			if ln.line_status in ("Supplier Stock Out", "Discontinued", "Cancelled by Supplier"):
				not_coming[ln.po3_item] = ln.line_status

	by_item = {}
	rows = {}
	for r in po.items:
		rows[r.name] = r
		by_item.setdefault(r.item_code, r.name)

	# goods already spoken for by another open shipment on this order
	in_transit = {}
	for other in frappe.get_all("Inbound Shipment V3",
			filters={"purchase_order_v3": po.name, "docstatus": 0,
					"name": ("!=", doc.name or "")},
			fields=["name"], limit_page_length=0):
		for si in frappe.get_all("Inbound Shipment V3 Item", filters={"parent": other.name},
				fields=["po3_item", "qty"], limit_page_length=0):
			if si.po3_item:
				in_transit[si.po3_item] = in_transit.get(si.po3_item, 0) + float(si.qty or 0)

	# empty grid -> offer what is still expected to arrive
	if not doc.items:
		for r in po.items:
			if r.line_status in ("Received", "Closed Short", "Cancelled", "Supplier Stock Out", "Discontinued"):
				continue
			if r.name in not_coming:
				continue
			p = promised.get(r.name)
			# in-transit counts as shipped here: the first wave has left the
			# supplier, so what is left to send is the back-ordered balance
			shipped = F(r.shipped_qty) + in_transit.get(r.name, 0)
			# A split line ships in two waves. Offer the confirmed-now portion until
			# that has actually shipped; after that the outstanding balance is what
			# is coming, so the whole ordered qty becomes the basis.
			backordered = (r.line_status == "Back-ordered") or (p and p.line_status in
				("Back-ordered", "Partial - Balance Back-ordered"))
			if p and backordered:
				now_qty = F(p.confirmed_qty)
				base = now_qty if shipped < now_qty else F(r.qty)
			elif p:
				base = F(p.confirmed_qty)
			else:
				base = F(r.qty)
			out = base - F(r.shipped_qty) - in_transit.get(r.name, 0)
			if out <= 0:
				continue
			d = doc.append("items", {})
			d.po3_item = r.name
			d.item_code = r.item_code
			d.qty = out
		if not doc.items:
			msg = ("Nothing left to ship on " + po.name
				+ " - every line is received, closed, already on another shipment, "
				+ "or the supplier said it is not coming.")
			if in_transit:
				msg = msg + "<br><br>Open shipments on this order already carry: " + ", ".join(
					frappe.get_all("Inbound Shipment V3",
						filters={"purchase_order_v3": po.name, "docstatus": 0,
								"name": ("!=", doc.name or "")},
						pluck="name", limit_page_length=0))
			frappe.throw(msg)

	total_qty = 0.0
	box_counts = {}
	warn_not_coming = []
	warn_over = []
	for d in doc.items:
		if not d.po3_item and d.item_code in by_item:
			d.po3_item = by_item[d.item_code]
		total_qty += F(d.qty)
		if d.box_no:
			box_counts[d.box_no] = box_counts.get(d.box_no, 0) + 1
		if d.po3_item in not_coming:
			warn_not_coming.append((d.item_code or "?") + " (" + not_coming[d.po3_item] + ")")
		p = promised.get(d.po3_item)
		if p:
			r = rows.get(d.po3_item)
			already = (F(r.shipped_qty) + in_transit.get(d.po3_item, 0)) if r else 0
			split = (r and r.line_status == "Back-ordered") or (p.line_status in
				("Back-ordered", "Partial - Balance Back-ordered"))
			# a split line is promised in full, just in two waves
			promised_total = F(r.qty) if (split and r) else F(p.confirmed_qty)
			allowed = promised_total - already
			if F(d.qty) > allowed + 0.000001:
				warn_over.append((d.item_code or "?") + ": shipping " + str(F(d.qty))
					+ " but only " + str(allowed) + " still due")

	# information, not obstruction - the goods are physically here either way
	if warn_not_coming:
		frappe.msgprint("<b>Heads up:</b> the confirmation says these were NOT coming, "
			+ "but they are on this shipment:<br>" + "<br>".join(warn_not_coming))
	if warn_over:
		frappe.msgprint("<b>Heads up:</b> more than the supplier confirmed:<br>"
			+ "<br>".join(warn_over))

	doc.total_qty = total_qty
	doc.total_boxes = len(doc.boxes or [])
	tw = 0.0
	for b in (doc.boxes or []):
		b.item_count = box_counts.get(b.box_no, 0)
		tw += F(b.weight_kg)
	doc.total_weight_kg = tw

	mirror_po3_status(po.name)

	# ---- carrier tracking links -------------------------------------
	# The template lives on the carrier's Supplier card so one edit fixes
	# every shipment, past and future.
	def track_url(carrier, tracking_no):
		if not carrier or not tracking_no:
			return None
		tpl = frappe.db.get_value("Supplier", carrier, "custom_tracking_url_template")
		if not tpl:
			return None
		num = str(tracking_no).strip()
		if "{tracking_no}" in tpl:
			return tpl.replace("{tracking_no}", num)
		return tpl + num

	def check_service(carrier, service, where):
		if not service:
			return
		owner = frappe.db.get_value("Carrier Service", service, "carrier")
		if carrier and owner and owner != carrier:
			frappe.throw(where + ": service '" + str(service) + "' belongs to "
				+ str(owner) + ", not " + str(carrier) + ".")

	check_service(doc.carrier, doc.carrier_service, "Shipment")
	doc.tracking_url = track_url(doc.carrier, doc.tracking_no)
	for b in doc.boxes:
		# a box with no carrier of its own rides on the shipment's
		if not b.carrier:
			b.carrier = doc.carrier
		if not b.carrier_service and b.carrier == doc.carrier:
			b.carrier_service = doc.carrier_service
		check_service(b.carrier, b.carrier_service, "Box " + str(b.box_no or b.idx))
		b.tracking_url = track_url(b.carrier, b.tracking_no)

	# transit days on the service suggest an arrival date, but never overwrite
	# one a human has already put in
	if doc.ship_date and doc.carrier_service and not doc.expected_arrival:
		days = frappe.db.get_value("Carrier Service", doc.carrier_service, "transit_days")
		if days:
			doc.expected_arrival = frappe.utils.add_days(doc.ship_date, int(days))

	# ---- a shipment with shipping details on it is not a draft ------
	if (doc.docstatus == 0 and doc.workflow_state in (None, "", "Draft")
			and frappe.db.exists("Inbound Shipment V3", doc.name)):
		# a new doc cannot be moved here - Frappe rejects the transition on
		# insert, so INS3 Auto In Transit picks it up afterwards instead
		has_track = 1 if doc.tracking_no else 0
		for b in doc.boxes:
			if b.tracking_no:
				has_track = 1
		if has_track or (doc.carrier and doc.ship_date):
			doc.workflow_state = "In Transit"
			frappe.msgprint("Shipping details added - moved to <b>In Transit</b>. "
				"It stays fully editable.")


# ---------------------------------------------------------------------------
# Migrated from Server Script "INS3 Auto In Transit"
# (DocType Event / After Insert on Inbound Shipment V3).
#
# A shipment created with tracking (or a carrier plus a ship date) is already
# on its way, so it opens as In Transit rather than Draft.
# ---------------------------------------------------------------------------
def auto_in_transit(doc):
	if doc.docstatus == 0 and doc.workflow_state in (None, "", "Draft"):
		has_track = 1 if doc.tracking_no else 0
		for b in doc.boxes:
			if b.tracking_no:
				has_track = 1
		if has_track or (doc.carrier and doc.ship_date):
			# set_value writes past the workflow transition check, which refuses
			# any state but Draft on a document that has just been created
			frappe.db.set_value("Inbound Shipment V3", doc.name,
				"workflow_state", "In Transit", update_modified=False)
			frappe.msgprint("Shipping details present - created as <b>In Transit</b>. "
				"It stays fully editable.")
