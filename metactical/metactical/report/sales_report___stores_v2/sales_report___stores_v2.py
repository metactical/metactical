# Copyright (c) 2023, Techlift Technologies and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe


def execute(filters=None):
    if not filters:
        filters = {}
    if filters.get('pos_profile'):
        warehouse, company = frappe.db.get_value("POS Profile", filters.get("pos_profile"), ["warehouse", "company"])
        filters["warehouse"] = warehouse
        filters["company"] = company

    conditions = get_conditions(filters)

    columns = get_column()
    data = []

    opening_closing = get_data(conditions, filters)
    for d in opening_closing:
        if d.qty > 0:
            transit_warehouse = get_transit_warehouse(d.warehouse)
            # Get WHS Actual Qty
            wh_actual = frappe.db.get_value(
                "Bin",
                {"warehouse": "W01-WHS-Active Stock - ICL", "item_code": d.item_code},
                "actual_qty"
            ) or 0.0
            # Get WHS Reserved Qty
            wh_res = frappe.db.get_value(
                "Bin",
                {"warehouse": "W01-WHS-Active Stock - ICL", "item_code": d.item_code},
                "reserved_qty"
            ) or 0.0
            item_barcodes = d.barcodes.split(',') if d.barcodes else []
            row = {
                'ifw_retailskusuffix': d.ifw_retailskusuffix,
                'item_code': d.item_code,
                'barcodes': ' | '.join([barcode for barcode in item_barcodes if barcode]),
                'ifw_location': d.ifw_location,
                'item_name': d.item_name,
                'supplier_part_number': frappe.db.get_value(
                    "Item Supplier",
                    {"parent": d.item_code},
                    "supplier_part_no"
                ),
                'closing': frappe.db.get_value(
                    "Bin",
                    {"warehouse": d.warehouse, "item_code": d.item_code},
                    "actual_qty"
                ) or 0.0,
                'stock_levels': wh_actual - wh_res,
                "in_transit": frappe.db.get_value(
                    "Bin", {"warehouse": transit_warehouse, "item_code": d.item_code},
                    "actual_qty"
                ) or 0,
                'sale': d.qty,
                'pos_profile': d.pos_profile,
                "button": (
                    '''
                    <button onClick="create_material_transfer(\'{}\', \'{}\', \'{}\')">
                        Create Material Transfer
                    </button>
                    '''
                    .format(filters.get("pos_profile", ""), filters.get("to_date"), filters.get("item_code", ""))
                )
            }

            if row['stock_levels'] > 0:
                data.append(row)

    return columns, data


def get_column():
    return [
        {
            "fieldname": "ifw_retailskusuffix",
            "label": "RetailSkuSuffix",
            "width": 120,
            "fieldtype": "Data",
        },
        {
            "fieldname": "item_code",
            "label": "ERPItemNo.",
            "width": 120,
            "fieldtype": "Link",
            "options": "Item",

        },
        {
            "fieldname": "barcodes",
            "label": "Barcode(s)",
            "width": 120,
            "fieldtype": "Data",
        },
        {
            "fieldname": "item_name",
            "label": "ItemName",
            "width": 100,
            "fieldtype": "Data",

        },
        {
            "fieldname": "supplier_part_number",
            "label": "SupplierSku",
            "width": 150,
            "fieldtype": "Data",

        },
        {
            "fieldname": "sale",
            "label": "QTYSold",
            "fieldtype": "Int",
            "width": 80,
        },
        {
            "fieldname": "closing",
            "label": "QTYLeft",
            "fieldtype": "Int",
            "width": 130,
        },
        {
            "fieldname": "stock_levels",
            "label": "WHSQty",
            "width": 120,
            "fieldtype": "Int",
        },
        {
            "fieldname": "ifw_location",
            "label": "WHSLocation",
            "fieldtype": "Data",
            "width": 120,
        },
        {
            "fieldname": "in_transit",
            "label": "InTrstQty",
            "width": 120,
            "fieldtype": "Int",
        },
        {
            "fieldname": "pos_profile",
            "label": "POSProfile",
            "fieldtype": "Link",
            "options": "POS Profile",
            "width": 150,
        },
        {
            "fieldname": "button",
            "fieldtype": "Data",
            "width": 200,
        }
    ]


def get_transit_warehouse(warehouse):
    # Get transit warehouse
    w_split = warehouse.split("-") if warehouse else []
    w_length = len(w_split)
    transit_warehouse = ""
    if w_split[-2] and w_split[-2].strip() == "Active Stock":
        for w in w_split:
            if w.strip() == "Active Stock":
                break
            transit_warehouse += w + "-"
    if transit_warehouse != "":
        transit_warehouse += "InTransit Stock - " + w_split[-1].strip()
    return transit_warehouse


def get_data(conditions, filters):
    query = f"""
    	select
       		sales_invoice_item.item_code,
			sales_invoice_item.item_name,
			item.ifw_retailskusuffix,
			item.ifw_location,
			sales_invoice_item.warehouse,
			sum(sales_invoice_item.qty) as qty,
			sales_invoice.pos_profile,
			sales_invoice.company,
			sales_invoice_item.uom,
			sales_invoice_item.stock_uom,
			sales_invoice_item.conversion_factor,
			GROUP_CONCAT(sales_invoice_item.barcode) as barcodes
		from `tabSales Invoice Item` sales_invoice_item
		inner join `tabSales Invoice` sales_invoice 
			on sales_invoice.name = sales_invoice_item.parent       
		inner join `tabItem` item 
			on sales_invoice_item.item_code = item.name
		Left Join `tabItem Barcode` item_barcode
			on item_barcode.parent = item.name
		where
			sales_invoice.docstatus = 1
			and is_pos =1
			and sales_invoice.posting_date = '{filters.get("to_date")}'
			{conditions}
		group by sales_invoice_item.item_code, sales_invoice.pos_profile
		order by sales_invoice_item.item_name, sales_invoice.pos_profile
    """

    data = frappe.db.sql(query, as_dict=1)

    return data


def get_conditions(filters, sales_order=None):
    conditions = ""
    if filters.get("item_code"):
        conditions += " and c.item_code = '{}'".format(filters.get("item_code"))
    if filters.get("pos_profile"):
        conditions += " and p.pos_profile = '{}'".format(filters.get("pos_profile"))
    return conditions


@frappe.whitelist()
def get_item_details(item, list_type="Selling"):
    cond = " and selling = 1"
    if list_type == "Buying": cond = " and buying = 1"
    rate = 0
    date = frappe.utils.nowdate()
    r = frappe.db.sql(
        "select price_list_rate from `tabItem Price` where '{}' between valid_from and valid_upto and item_code = '{}' {} limit 1".format(
            date, item, cond))
    if r:
        if r[0][0]:
            rate = r[0][0]
    else:
        r = frappe.db.sql(
            "select price_list_rate from `tabItem Price` where (valid_from <= '{}' or valid_upto >= '{}') and item_code = '{}' {} limit 1".format(
                date, date, item, cond))
        if r:
            if r[0][0]:
                rate = r[0][0]
        else:
            r = frappe.db.sql(
                "select price_list_rate from `tabItem Price` where valid_from IS NULL and valid_upto IS NULL and item_code = '{}' {} limit 1".format(
                    item, cond))
            if r:
                if r[0][0]:
                    rate = r[0][0]
    return rate


@frappe.whitelist()
def create_material_transfer(**args):
    args = frappe._dict(args)
    filters = {}
    if args.pos_profile != "":
        filters["pos_profile"] = args.pos_profile
    if args.to_date != "":
        filters["to_date"] = args.to_date
    if args.item_code != "":
        filters["item_code"] = args.item_code

    conditions = get_conditions(filters)
    init_data = get_data(conditions, filters)
    source_warehouse = "W01-WHS-Active Stock - " + frappe.db.get_value("Company", init_data[0].company, "abbr")
    doc = frappe.new_doc("Stock Entry")
    doc.update({
        "stock_entry_type": "Material Transfer",
        "ais_from_report": 1
    })
    for row in init_data:
        wh_actual = frappe.db.get_value("Bin", {"warehouse": source_warehouse, "item_code": row.item_code},
                                        "actual_qty") or 0.0
        wh_res = frappe.db.get_value("Bin", {"warehouse": source_warehouse, "item_code": row.item_code},
                                     "reserved_qty") or 0.0
        stock_levels = wh_actual - wh_res
        transit_warehouse = get_transit_warehouse(row.warehouse)
        if stock_levels > 0 and transit_warehouse != "":
            doc.append("items", {
                "s_warehouse": source_warehouse,
                "t_warehouse": transit_warehouse,
                "item_code": row.item_code,
                "qty": row.qty,
                "uom": row.uom,
                "stock_uom": row.stock_uom,
                "conversion_factor": row.conversion_factor
            })
    doc.insert(ignore_permissions=True)
    return doc
