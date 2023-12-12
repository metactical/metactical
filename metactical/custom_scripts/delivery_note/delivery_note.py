import frappe
from metactical.api.shipstation import create_shipstation_orders, delete_order
from erpnext.stock.doctype.delivery_note.delivery_note import DeliveryNote
from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice

def on_update(self, method):
	if self.docstatus == 0:
		#For shipstation
		create_shipstation_orders(self.name)
	
def on_trash(self, method):
	if self.docstatus == 0 and self.ais_shipstation_order_ids is not None:
		delete_order(self.name)
		
def on_cancel(self, method):
	#super(DeliveryNote, self).on_cancel()

	self.check_sales_order_on_hold_or_close("against_sales_order")
	self.check_next_docstatus()

	self.update_prevdoc_status()
	self.update_billing_status()

	# Updating stock ledger should always be called after updating prevdoc status,
	# because updating reserved qty in bin depends upon updated delivered qty in SO
	self.update_stock_ledger()

	self.cancel_packing_slips()

	self.make_gl_entries_on_cancel()
	
	# Metactical Customization: Return picked qty to previous one if is return
	if self.is_return == 1 and self.pick_list:
		sales_orders = []
		for row in self.items:
			if row.against_sales_order:
				if row.against_sales_order not in sales_orders:
					sales_orders.append(row.against_sales_order)
					
				#Get the picked qty
				is_stock_item = frappe.db.get_value("Item", row.item_code, "is_stock_item")
				if is_stock_item == 1:
					picked_qty = frappe.db.get_value("Sales Order Item", row.so_detail, "picked_qty")
					if picked_qty < abs(row.qty):
						new_qty = picked_qty + abs(row.qty)
						frappe.db.set_value("Sales Order Item", row.so_detail, "picked_qty", new_qty)
						
		for sales_order in sales_orders:
			doc = frappe.get_doc("Sales Order", sales_order)
			doc.update_picking_status()
	
	#Cancel on shipstation
	create_shipstation_orders(self.name, True)
	
def on_submit(self, method):
	#check if delivery note doesn't have a sales invoice
	if self.ais_skip_auto_invoice == 1:
		return
	
	if self.per_billed == 100:
		return
		
	# Metactical Customization: If is return, set picked qty in sales order to be zero
	if self.is_return == 1 and self.pick_list:
		sales_orders = []
		for row in self.items:
			if row.against_sales_order:
				if row.against_sales_order not in sales_orders:
					sales_orders.append(row.against_sales_order)
				#Get the picked qty
				picked_qty = frappe.db.get_value("Sales Order Item", row.so_detail, "picked_qty")
				if picked_qty > 0:
					new_qty = picked_qty - abs(row.qty)
					frappe.db.set_value("Sales Order Item", row.so_detail, "picked_qty", new_qty)
		for sales_order in sales_orders:
			doc = frappe.get_doc("Sales Order", sales_order)
			doc.update_picking_status()
	elif self.is_return == 0:
		for row in self.items:
			if row.against_sales_order and row.against_sales_invoice is None:
				sales_order = frappe.get_doc('Sales Order', row.against_sales_order)
				
				#check sales order is fully delivered and not billed
				if sales_order.per_billed != 0 or sales_order.per_delivered != 100:
					break
				
				#check sales order is fully paid
				if sales_order.grand_total != sales_order.advance_paid:
					break
				sales_invoice = frappe.new_doc('Sales Invoice')
				sales_invoice.update({'ignore_pricing_rule': sales_order.ignore_pricing_rule})
				sales_invoice = make_sales_invoice(row.against_sales_order, sales_invoice)
				sales_invoice.update({"ais_automated_creation": 1, "disable_rounded_total": 1})
				
				#Get payment entry with Sales Order and add it to advance paid
				sales_invoice.set_advances()
				sales_invoice.submit()
