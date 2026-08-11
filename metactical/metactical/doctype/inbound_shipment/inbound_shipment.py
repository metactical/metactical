import frappe
from frappe import _
from frappe.model.document import Document


class InboundShipment(Document):
	def validate(self):
		self._validate_against_po()
		self._validate_shipped_qty()

	def on_submit(self):
		self._auto_create_purchase_receipt()

	def _validate_against_po(self):
		po_items = {
			row.name: row
			for row in frappe.get_doc("Purchase Order", self.purchase_order).items
		}
		for line in self.items:
			if line.po_detail not in po_items:
				frappe.throw(_("Row #{0}: PO Detail {1} does not belong to PO {2}").format(
					line.idx, line.po_detail, self.purchase_order
				))

	def _validate_shipped_qty(self):
		if not self.supplier_order_confirmation:
			return

		soc_qtys = {
			row.name: row.confirmed_qty
			for row in frappe.get_doc("Supplier Order Confirmation", self.supplier_order_confirmation).items
		}
		for line in self.items:
			if line.soc_detail and line.soc_detail in soc_qtys:
				if line.shipped_qty > soc_qtys[line.soc_detail]:
					frappe.msgprint(
						_("Row #{0}: Shipped Qty {1} exceeds confirmed Qty {2} for {3}").format(
							line.idx, line.shipped_qty, soc_qtys[line.soc_detail], line.item_code
						),
						indicator="orange",
						alert=True,
					)

	def _auto_create_purchase_receipt(self):
		# Whole-shipment Draft PR, created automatically the moment the shipment
		# is submitted. Per-box PRs (split receiving) remain a manual action via
		# the doctype's "Create > Purchase Receipt (Select Box)" button.
		from metactical.custom_scripts.purchase_order.purchase_receipt_from_source import (
			make_purchase_receipt_from_shipment,
		)

		try:
			pr = make_purchase_receipt_from_shipment(self.name)
		except frappe.ValidationError:
			# Nothing outstanding to receive (e.g. already fully received via boxes).
			return
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Inbound Shipment auto Purchase Receipt failed")
			frappe.msgprint(
				_("Could not auto-create a Purchase Receipt for {0}. Use the Create button manually.").format(self.name),
				indicator="orange",
				alert=True,
			)
			return

		pr.insert(ignore_permissions=True)
		frappe.db.set_value(self.doctype, self.name, "draft_purchase_receipt", pr.name)
		frappe.msgprint(
			_("Draft Purchase Receipt {0} created.").format(
				frappe.utils.get_link_to_form("Purchase Receipt", pr.name)
			),
			alert=True,
			indicator="green",
		)
