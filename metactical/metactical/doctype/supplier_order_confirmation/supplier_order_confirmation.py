import frappe
from frappe import _
from frappe.model.document import Document


class SupplierOrderConfirmation(Document):
	def validate(self):
		self._validate_against_po()

	def on_submit(self):
		self._check_for_discrepancies()

	def _validate_against_po(self):
		po_items = {
			row.name: row
			for row in frappe.get_doc("Purchase Order", self.purchase_order).items
		}
		for line in self.items:
			if line.po_detail and line.po_detail not in po_items:
				frappe.throw(_("Row #{0}: PO Detail {1} does not belong to PO {2}").format(
					line.idx, line.po_detail, self.purchase_order
				))
			po_row = po_items.get(line.po_detail)
			if po_row and line.confirmed_qty > po_row.qty:
				frappe.msgprint(
					_("Row #{0}: Confirmed Qty {1} exceeds ordered Qty {2} for {3}").format(
						line.idx, line.confirmed_qty, po_row.qty, line.item_code
					),
					indicator="orange",
					alert=True,
				)

	def _check_for_discrepancies(self):
		has_discrepancy = any(
			line.line_status in ("Partial", "Out of Stock", "Back-ordered", "Discontinued", "Substituted")
			or (line.confirmed_rate and line.confirmed_rate != self._po_rate(line.po_detail))
			for line in self.items
		)
		if has_discrepancy:
			frappe.db.set_value(self.doctype, self.name, "workflow_state", "Discrepancy Hold")

	def _po_rate(self, po_detail):
		if not po_detail:
			return 0
		return frappe.db.get_value("Purchase Order Item", po_detail, "rate") or 0
