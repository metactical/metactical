import frappe
from metactical.api.shipstation import create_shipstation_orders

def on_update(self, method):
	frappe.msgprint("After save called")
	create_shipstation_orders(self.name)
