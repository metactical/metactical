# Copyright (c) 2024, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import getdate


def execute(filters=None):
    print("filters", filters)

    columns, data = get_columns(), get_data(filters)
    # update date format
    for row in data:
        row["date_changed"] = getdate(row.get("date_changed")).strftime("%d-%b-%y") if row.get("date_changed") else ""

    return columns, data


def get_columns():
    return [
        {
            "fieldname": "ifw_retailskusuffix",
            "label": _("Retail Sku Suffix"),
            "width": 120,
            "fieldtype": "Data",
        },
        {
            "fieldname": "item_code",
            "label": _("ERP Item No."),
            "width": 120,
            "fieldtype": "Link",
            "options": "Item",

        },
        {
            "fieldname": "item_name",
            "label": _("Item Name"),
            "width": 100,
            "fieldtype": "Data",

        },
        {
            "fieldname": "barcodes",
            "label": _("Barcode(s)"),
            "width": 120,
            "fieldtype": "Data",
        },
        {
            "fieldname": "old_price",
            "label": _("Old Price"),
            "width": 120,
            "fieldtype": "Currency",
        },
        {
            "fieldname": "current_price",
            "label": _("Current Price"),
            "width": 120,
            "fieldtype": "Currency",
        },
        {
            "label": _("SUP Cost"),
            "fieldname": "item_cost",
            "fieldtype": "Currency",
            "width": 100,
        },
        {
            "fieldname": "date_changed",
            "label": _("Date Changed"),
            "width": 120,
            "fieldtype": "Data",
        },
        {
            "fieldname": "changed_by",
            "label": _("Changed By"),
            "width": 120,
            "fieldtype": "Link",
            "options": "User",
        }
    ]


def get_data(filters):
    """
    From Item, Item Price, and Item Barcode Doctypes get the following:
    - Item Code
    - Item Name
    - Old Price
    - New Price
    - Date Changed
    - Changed By
    - Barcodes
    - Retail Sku Suffix
    """
    from_date = filters.get("from_date")
    to_date = filters.get("to_date")
    item_code = filters.get("item_code")

    conditions = []

    if from_date and to_date:
        conditions.append(f"modified BETWEEN '{from_date}' AND '{to_date}'")
    elif from_date:
        conditions.append(f"modified >= '{from_date}'")
    elif to_date:
        conditions.append(f"modified <= '{to_date}'")

    if item_code:
        conditions.append(f"item_code = '{item_code}'")

    where_clause = "WHERE " + (" AND ".join(conditions) if conditions else "")

    query = f"""
        WITH RankedPrices AS (
            SELECT
                item_code,
                price_list,
                currency,
                price_list_rate,
                modified,
                modified_by,
                LAG(price_list_rate) OVER (PARTITION BY item_code ORDER BY modified) AS previous_price,
                ROW_NUMBER() OVER (PARTITION BY item_code ORDER BY modified DESC) AS row_num
            FROM
                `tabItem Price`
            {where_clause}
        )
        SELECT
            item.ifw_retailskusuffix AS ifw_retailskusuffix,
            item.item_code AS item_code,
            item.item_name AS item_name,
            barcode.barcode AS barcodes,
            RankedPrices.previous_price AS old_price,
            RankedPrices.price_list_rate AS current_price,
            RankedPrices.price_list,
            RankedPrices.modified AS date_changed,
            RankedPrices.modified_by AS changed_by,
            RankedPrices.currency
        FROM
            RankedPrices
        JOIN
            `tabItem` AS item ON RankedPrices.item_code = item.item_code
        JOIN 
            `tabItem Barcode` AS barcode ON RankedPrices.item_code = barcode.parent
        WHERE
          RankedPrices.row_num = 1;
    """

    try:
        data = frappe.db.sql(query, as_dict=True, debug=True)
        return data
    except Exception as e:
        frappe.log_error(f"Error getting data for Daily Item Updates Report: {e}")
        raise e

