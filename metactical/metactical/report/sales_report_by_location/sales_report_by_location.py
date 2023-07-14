# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe

def execute(filters=None):
    data = []
    columns = [
        {"label": "Brand", "fieldname": "brand", "fieldtype": "Link", "options": "Brand"},
        {"label": "Supplier", "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier"},
        {"label": "Retail SKU", "fieldname": "retail_sku", "fieldtype": "Data"},
        {"label": "Location", "fieldname": "location", "fieldtype": "Link", "options": "Warehouse"},
        {"label": "QOH for Location", "fieldname": "qoh_location", "fieldtype": "Float"},
        {"label": "TQOH for All Locations", "fieldname": "tqoh_all_locations", "fieldtype": "Float"},
        {"label": "Retail Price", "fieldname": "retail_price", "fieldtype": "Currency"},
        {"label": "Cost", "fieldname": "cost", "fieldtype": "Currency"},
        {"label": "Qty Sold", "fieldname": "qty_sold", "fieldtype": "Float"}
    ]

    warehouse = filters.get("warehouse")
    supplier = filters.get("supplier")
    from_date = filters.get("from_date")
    to_date = filters.get("to_date")
    
    where_extra = ""
    if warehouse and warehouse != "":
        where_extra += " AND sii.warehouse = '{warehouse}'".format(warehouse = warehouse)
    
    if supplier and supplier != "":
        where_extra += " AND defaults.default_supplier = '{supplier}'".format(supplier = supplier)

    # Query sales orders and related information
    data = frappe.db.sql("""
        SELECT
            sii.item_code AS item_code,
            i.brand AS brand,
            defaults.default_supplier AS supplier,
            i.ifw_retailskusuffix AS retail_sku,
            sii.warehouse AS location,
            b.actual_qty AS qoh_location,
            (SELECT SUM(actual_qty) FROM `tabBin` WHERE item_code = i.name) AS tqoh_all_locations,
            ip.price_list_rate AS retail_price,
            i.valuation_rate AS cost,
            SUM(sii.qty) AS qty_sold
        FROM
            `tabSales Invoice` AS si
        JOIN
            `tabSales Invoice Item` AS sii ON si.name = sii.parent
        JOIN
            `tabItem` AS i ON sii.item_code = i.name
        JOIN
            `tabItem Default` AS defaults ON defaults.parent = i.name
        JOIN
            `tabBin` AS b ON i.name = b.item_code AND b.warehouse = sii.warehouse
        JOIN
            `tabItem Price` ip on ip.item_code = i.item_code and ip.price_list = "RET - Camo"
        WHERE
            si.docstatus = 1 AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
    """ + where_extra + 
    """
		GROUP BY 
			item_code, brand, supplier, retail_sku, location, qoh_location, 
			tqoh_all_locations, retail_price, cost
    """, {"from_date": from_date, "to_date": to_date}, as_dict=True)

    return columns, data
