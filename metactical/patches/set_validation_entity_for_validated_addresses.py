import frappe


def execute():
	frappe.db.sql("""
		UPDATE `tabAddress`
		SET custom_ais_validation_entity = 'Shipstation'
		WHERE custom_ais_address_verified = 'Validated'
		  AND (custom_ais_validation_entity IS NULL OR custom_ais_validation_entity = '')
	""")
