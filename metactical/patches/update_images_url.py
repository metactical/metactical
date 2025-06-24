import frappe

def execute():
    frappe.db.sql("""
        UPDATE `tabItem`
        SET image = CONCAT('https://metactical.b-cdn.net/images/products/small/', item_code, '.jpg')
        """)
    frappe.db.commit()