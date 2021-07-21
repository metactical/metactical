import frappe
from metactical.api.shipstation import create_shipstation_orders

def on_update(self, method):
	create_shipstation_orders(self.name)
