import frappe
from frappe import _
from frappe.model.document import Document


class InboundShipment(Document):
	def validate(self):
		self._validate_shipped_qty()

	def on_submit(self):
		self._mark_boxes_received()

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

	def _mark_boxes_received(self):
		for box in self.boxes:
			frappe.db.set_value("Inbound Shipment Box", box.name, "received", 1)
