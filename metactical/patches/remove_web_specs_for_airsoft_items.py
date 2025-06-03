import frappe
from frappe.utils.fixtures import sync_fixtures

def execute():
    item_groups = ["Airsoft Pistols", "Airsoft Rifles", "Airsoft Shotguns", "Airsoft SMGs", "Airsoft Sniper Rifles", "Airsoft Revolvers"]
    for item_group in item_groups:
        frappe.db.sql("""
            DELETE `tabMT Item Website Specification` 
            FROM `tabMT Item Website Specification`
            JOIN `tabItem` ON `tabItem`.name = `tabMT Item Website Specification`.parent
            WHERE `tabItem`.item_group = %s AND `tabItem`.disabled = 0
        """, (item_group,))
    frappe.db.commit()