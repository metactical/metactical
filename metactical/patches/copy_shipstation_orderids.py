import frappe
from frappe.utils.fixtures import sync_fixtures

def execute():
	sync_fixtures()
	frappe.reload_doc('stock', 'doctype', 'Delivery Note')
	delivery_notes = frappe.db.sql('''SELECT name FROM `tabDelivery Note` WHERE ais_shipstation_orderid IS NOT NULL''', as_dict=1)
	shipstation_settings = frappe.db.sql('''SELECT name FROM `tabShipstation Settings` LIMIT 1''', as_dict=1)
	for row in delivery_notes:
		delivery_note = frappe.get_doc('Delivery Note', row.name)
		shipstation_orderid = frappe.new_doc('Shipstation Order ID', delivery_note, 'ais_shipstation_order_ids')
		shipstation_orderid.update({
			"settings_id": shipstation_settings[0].name,
			"shipstation_order_id": delivery_note.ais_shipstation_orderid
		})
		shipstation_orderid.save()
