# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe

def execute(filters=None):
    data = []
    columns = [
        {"label": "Sales Order", "fieldname": "sales_order", "fieldtype": "Link", "options": "Sales Order"},
        {"label": "Transaction Date", "fieldname": "transaction_date", "fieldtype": "Date"},
        {"label": "Customer", "fieldname": "customer", "fieldtype": "Link", "options": "Customer"},
        {"label": "Item Code", "fieldname": "item_code", "fieldtype": "Link", "options": "Item"},
        {"label": "Quantity", "fieldname": "quantity", "fieldtype": "Float"},
        {"label": "Rate", "fieldname": "rate", "fieldtype": "Currency"},
        {"label": "Amount", "fieldname": "amount", "fieldtype": "Currency"},
        {"label": "Brand", "fieldname": "brand", "fieldtype": "Link", "options": "Brand"},
        {"label": "Supplier", "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier"},
        {"label": "Retail SKU", "fieldname": "retail_sku", "fieldtype": "Data"},
        {"label": "QOH for Location", "fieldname": "qoh_location", "fieldtype": "Float"},
        {"label": "TQOH for All Locations", "fieldname": "tqoh_all_locations", "fieldtype": "Float"},
        {"label": "Retail Price", "fieldname": "retail_price", "fieldtype": "Currency"},
        {"label": "Cost", "fieldname": "cost", "fieldtype": "Currency"},
        {"label": "Qty Sold", "fieldname": "qty_sold", "fieldtype": "Float"},
    ]

    warehouse = filters.get("warehouse") 
    from_date = filters.get("from_date")
    to_date = filters.get("to_date")

    # Query sales orders and related information
    sales_orders = frappe.db.sql("""
        SELECT
            so.name AS sales_order,
            so.transaction_date AS transaction_date,
            so.customer AS customer,
            si.item_code AS item_code,
            si.qty AS quantity,
            si.rate AS rate,
            si.amount AS amount,
            i.brand AS brand,
            i.supplier AS supplier,
            i.retail_sku AS retail_sku,
            b.actual_qty AS qoh_location,
            (SELECT SUM(actual_qty) FROM `tabBin` WHERE item_code = i.name) AS tqoh_all_locations,
            i.retail_price AS retail_price,
            i.standard_cost AS cost,
            si.qty_sold AS qty_sold
        FROM
            `tabSales Order` AS so
        JOIN
            `tabSales Order Item` AS si ON so.name = si.parent
        JOIN
            `tabItem` AS i ON si.item_code = i.name
        JOIN
            `tabBin` AS b ON i.name = b.item_code AND b.warehouse = %(warehouse)s
        WHERE
            so.docstatus = 1  -- Approved sales orders
            AND so.transaction_date BETWEEN %(from_date)s AND %(to_date)s
    """, {"warehouse": warehouse, "from_date": from_date, "to_date": to_date}, as_dict=True)

    # Prepare data for the report
    for order in sales_orders:
        data.append({
            "sales_order": order.sales_order,
            "transaction_date": order.transaction_date,
            "customer": order.customer,
            "item_code": order.item_code,
            "quantity": order.quantity,
            "rate": order.rate,
            "amount": order.amount,
            "brand": order.brand,
            "supplier": order.supplier,
            "retail_sku": order.retail_sku,
            "qoh_location": order.qoh_location,
            "tqoh_all_locations": order.tqoh_all_locations,
            "retail_price": order.retail_price,
            "cost": order.cost,
            "qty_sold": order.qty_sold,
        })

    return columns, data
