import frappe
from metactical.api.shipstation import create_shipstation_orders, delete_order
from erpnext.stock.doctype.delivery_note.delivery_note import DeliveryNote

def on_update(self, method):
	if self.docstatus == 0:
		create_shipstation_orders(self.name)
	
def on_trash(self, method):
	if self.docstatus == 0 and self.ais_shipstation_orderid is not None:
		delete_order(self.name)
		
def on_cancel(self, method):
	super(DeliveryNote, self).on_cancel()

	self.check_sales_order_on_hold_or_close("against_sales_order")
	self.check_next_docstatus()

	self.update_prevdoc_status()
	self.update_billing_status()

	# Updating stock ledger should always be called after updating prevdoc status,
	# because updating reserved qty in bin depends upon updated delivered qty in SO
	self.update_stock_ledger()

	self.cancel_packing_slips()

	self.make_gl_entries_on_cancel()
	
	#Cancel on shipstation
	create_shipstation_orders(self.name, True)
