# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe import _, scrub
from frappe.utils import getdate, flt, add_to_date, add_days
from six import iteritems
from erpnext.accounts.utils import get_fiscal_year


def execute(filters=None):
    return Analytics(filters).run()


class Analytics(object):
    def __init__(self, filters=None):
        self.filters = frappe._dict(filters or {})

    def run(self):
        self.get_columns()
        self.get_data()
        skip_total_row = 0
        return self.columns, self.data, None, None, None, skip_total_row

    def get_columns(self):
        self.columns = [
            {
                "label": _("RetailSkuSuffix"),
                "fieldname": "ifw_retailskusuffix",
                "fieldtype": "Data",
                "width": 150,
            },
            {
                "label": "ERPNextItemCode",
                "options": "Item",
                "fieldname": "entity",
                "fieldtype": "Link",
                "width": 150,
                "align": "left",
            },
            {
                "label": _("Barcode"),
                "fieldname": "barcode",
                "fieldtype": "Data",
                "width": 150,
                "align": "left",
            },
            {
                "label": _("ItemName"),
                "fieldname": "entity_name",
                "fieldtype": "Data",
                "width": 300,
            },
            {
                "label": _("Tags"),
                "fieldname": "tag",
                "fieldtype": "Data",
                "width": 100,
            },
            {
                "label": _("Rate"),
                "fieldname": "rate",
                "fieldtype": "Currency",
                "width": 100,
            },
            {
                "label": _("Discointinued"),
                "fieldname": "item_discontinued",
                "fieldtype": "Boolean",
                "width": 100,
                "default": False,
            },
            {
                "label": _("ETA"),
                "fieldname": "eta",
                "fieldtype": "Date",
                "width": 100,
            },
            {
                "label": _("DateLastReceived"),
                "fieldname": "date_last_received",
                "fieldtype": "DateTime",
                "width": 200,
            },
            {
                "label": _("Cost"),
                "fieldname": "item_cost",
                "fieldtype": "Currency",
                "width": 100,
            },
            {
                "label": _("Suplier SKU"),
                "fieldname": "supplier_sku",
                "fieldtype": "Data",
                "width": 100,
            },
            {
                "label": _("Supplier Name"),
                "fieldname": "supplier_name",
                "fieldtype": "Link",
                "options": "Supplier",
                "width": 200,
            },
            {
                "label": _("W01-WHS-Active Stock - ICL"),
                "fieldname": "wh_whs",
                "fieldtype": "Link",
                "options": "Supplier",
                "width": 200,
            },
            {
                "label": _("R05-DTN-Active Stock - ICL"),
                "fieldname": "wh_dtn",
                "fieldtype": "Link",
                "options": "Supplier",
                "width": 200,
            },
            {
                "label": _("R07-Queen-Active Stock - ICL"),
                "fieldname": "wh_queen",
                "fieldtype": "Link",
                "options": "Supplier",
                "width": 200,
            },
            {
                "label": _("R06-AMB-Active Stock - ICL"),
                "fieldname": "wh_amb",
                "fieldtype": "Link",
                "options": "Supplier",
                "width": 200,
            },
            {
                "label": _("R04-Mon-Active Stock - ICL"),
                "fieldname": "wh_mon",
                "fieldtype": "Link",
                "options": "Supplier",
                "width": 200,
            },
            {
                "label": _("R03-Vic-Active Stock - ICL"),
                "fieldname": "wh_vic",
                "fieldtype": "Link",
                "options": "Supplier",
                "width": 200,
            },
            {
                "label": _("R02-Edm-Active Stock - ICL"),
                "fieldname": "wh_edm",
                "fieldtype": "Link",
                "options": "Supplier",
                "width": 200,
            },
            {
                "label": _("R01-Gor-Active Stock - ICL"),
                "fieldname": "wh_gor",
                "fieldtype": "Link",
                "options": "Supplier",
                "width": 200,
            },
            {
                "label": _("TotalQOH"),
                "fieldname": "total_actual_qty",
                "fieldtype": "Data",
                "width": 140,
            },
            {
                "label": _("Material Request"),
                "fieldname": "material_request",
                "fieldtype": "Data",
                "width": 200,
            },
            {
                "label": _("Expected PO Nos"),
                "fieldname": "expected_pos",
                "fieldtype": "Data",
                "width": 240,
            },
            {
                "label": _("ETA date PO"),
                "fieldname": "po_eta",
                "fieldtype": "Data",
                "width": 200,
            },
            {
                "label": _("PreviousYSale"),
                "fieldname": "previous_year_sale",
                "fieldtype": "Float",
                "width": 140,
            },
            {
                "label": _("CurrentYearSales"),
                "fieldname": "total",
                "fieldtype": "Float",
                "width": 140,
            },
            {
                "label": _("TotalSold12Months"),
                "fieldname": "last_twelve_months",
                "fieldtype": "Float",
                "width": 140,
            },
        ]

        month_field_names = {
            "January": "jan",
            "February": "feb",
            "March": "mar",
            "April": "apr",
            "May": "may",
            "June": "jun",
            "July": "jul",
            "August": "aug",
            "September": "sep",
            "October": "oct",
            "November": "nov",
            "December": "dece",
        }
        current_year = frappe.utils.datetime.datetime.today().year
        for month_name in month_field_names:
            self.columns.append(
                {
                    "label": _(str(current_year) + "_Sold" + month_name),
                    "fieldname": month_field_names[month_name],
                    "fieldtype": "Float",
                    "width": 120,
                }
            )
        self.columns.extend(
            [
                {
                    "label": _("SoldLast10Days"),
                    "fieldname": "sold_last_ten_days",
                    "fieldtype": "Float",
                    "width": 140,
                },
                {
                    "label": _("SoldLast30Days"),
                    "fieldname": "sold_last_thirty_days",
                    "fieldtype": "Float",
                    "width": 140,
                },
                {
                    "label": _("SoldLast60Days"),
                    "fieldname": "sold_last_sixty_days",
                    "fieldtype": "Float",
                    "width": 140,
                    "default": False,
                },
                {
                    "label": _("DateLastSold"),
                    "fieldname": "last_sold_date",
                    "fieldtype": "Date",
                    "width": 100,
                },
            ]
        )

    def get_data(self):
        current_date = frappe.utils.datetime.date.today()
        start_date = current_date.replace(day=1, month=1, year=current_date.year - 1)
        end_date = start_date.replace(month=12, day=31, year=start_date.year + 1)
        query = """                
SELECT sit1.item_code,
    sit1.total,
    sit1.previous_year_sale,
    sit1.sold_last_ten_days,
    sit1.sold_last_thirty_days,
    sit1.sold_last_sixty_days,
    sit1.last_twelve_months,
    sit1.last_sold_date,
    sit1.jan,
    sit1.feb,
    sit1.mar,
    sit1.apr,
    sit1.may,
    sit1.jun,
    sit1.jul,
    sit1.aug,
    sit1.sep,
    sit1.oct,
    sit1.nov,
    sit1.dece,
    sit1.item_code as entity,
    sit1.item_name as entity_name,
    sit1.stock_uom,
    sit1.stock_qty as value_field,
    sit1.posting_date,
    ip1.price_list_rate as rate,
    ib1.barcode,
    is1.supplier as supplier_name,
    is1.supplier_part_no as supplier_sku,
    pit1.last_pi_date as date_last_received,
    pit1.rate as item_cost,
    IFNULL(bin1.actual_qty, 0) as total_actual_qty,
    IFNULL(bin1.wh_whs, 0) as wh_whs,
    IFNULL(bin1.wh_dtn, 0) as wh_dtn,
    IFNULL(bin1.wh_queen, 0) as wh_queen,
    IFNULL(bin1.wh_amb, 0) as wh_amb,
    IFNULL(bin1.wh_vic, 0) as wh_vic,
    IFNULL(bin1.wh_gor, 0) as wh_gor,
    IFNULL(bin1.wh_edm, 0) as wh_edm,
    mri1.material_request,
    poi1.expected_pos,
    poi1.po_eta,
    tl1.tag,
    it.ifw_retailskusuffix as ifw_retailskusuffix
FROM (
        select SUM(
                CASE
                    when YEAR(si.posting_date) = YEAR(CURRENT_DATE()) then sit.stock_qty
                    else 0
                end
            ) total,
            SUM(
                CASE
                    when YEAR(si.posting_date) = YEAR(CURRENT_DATE()) -1 then sit.stock_qty
                    else 0
                end
            ) previous_year_sale,
            SUM(
                CASE
                    when DATEDIFF(CURRENT_DATE(), si.posting_date) <= 10 then sit.stock_qty
                    else 0
                end
            ) sold_last_ten_days,
            SUM(
                CASE
                    when DATEDIFF(CURRENT_DATE(), si.posting_date) <= 30 then sit.stock_qty
                    else 0
                end
            ) sold_last_thirty_days,
            SUM(
                CASE
                    when DATEDIFF(CURRENT_DATE(), si.posting_date) <= 60 then sit.stock_qty
                    else 0
                end
            ) sold_last_sixty_days,
            SUM(
                CASE
                    when DATEDIFF(CURRENT_DATE(), si.posting_date) <= 365 then sit.stock_qty
                    else 0
                end
            ) last_twelve_months,
            MAX(si.posting_date) as last_sold_date,
            SUM(
                CASE
                    when (
                        MONTH(si.posting_date) = 1
                        and (YEAR(si.posting_date) = YEAR(CURRENT_DATE()))
                    ) then sit.stock_qty
                    else 0
                end
            ) jan,
            SUM(
                CASE
                    when (
                        MONTH(si.posting_date) = 2
                        and (YEAR(si.posting_date) = YEAR(CURRENT_DATE()))
                    ) then sit.stock_qty
                    else 0
                end
            ) feb,
            SUM(
                CASE
                    when (
                        MONTH(si.posting_date) = 3
                        and (YEAR(si.posting_date) = YEAR(CURRENT_DATE()))
                    ) then sit.stock_qty
                    else 0
                end
            ) mar,
            SUM(
                CASE
                    when (
                        MONTH(si.posting_date) = 4
                        and (YEAR(si.posting_date) = YEAR(CURRENT_DATE()))
                    ) then sit.stock_qty
                    else 0
                end
            ) apr,
            SUM(
                CASE
                    when (
                        MONTH(si.posting_date) = 5
                        and (YEAR(si.posting_date) = YEAR(CURRENT_DATE()))
                    ) then sit.stock_qty
                    else 0
                end
            ) may,
            SUM(
                CASE
                    when (
                        MONTH(si.posting_date) = 6
                        and (YEAR(si.posting_date) = YEAR(CURRENT_DATE()))
                    ) then sit.stock_qty
                    else 0
                end
            ) jun,
            SUM(
                CASE
                    when (
                        MONTH(si.posting_date) = 7
                        and (YEAR(si.posting_date) = YEAR(CURRENT_DATE()))
                    ) then sit.stock_qty
                    else 0
                end
            ) jul,
            SUM(
                CASE
                    when (
                        MONTH(si.posting_date) = 8
                        and (YEAR(si.posting_date) = YEAR(CURRENT_DATE()))
                    ) then sit.stock_qty
                    else 0
                end
            ) aug,
            SUM(
                CASE
                    when (
                        MONTH(si.posting_date) = 9
                        and (YEAR(si.posting_date) = YEAR(CURRENT_DATE()))
                    ) then sit.stock_qty
                    else 0
                end
            ) sep,
            SUM(
                CASE
                    when (
                        MONTH(si.posting_date) = 10
                        and (YEAR(si.posting_date) = YEAR(CURRENT_DATE()))
                    ) then sit.stock_qty
                    else 0
                end
            ) oct,
            SUM(
                CASE
                    when (
                        MONTH(si.posting_date) = 11
                        and (YEAR(si.posting_date) = YEAR(CURRENT_DATE()))
                    ) then sit.stock_qty
                    else 0
                end
            ) nov,
            SUM(
                CASE
                    when (
                        MONTH(si.posting_date) = 12
                        and (YEAR(si.posting_date) = YEAR(CURRENT_DATE()))
                    ) then sit.stock_qty
                    else 0
                end
            ) dece,
            sit.item_code,
            sit.stock_qty,
            sit.item_name,
            sit.stock_uom,
            si.posting_date
        from `tabSales Invoice` si
            inner join `tabSales Invoice Item` sit on si.name = sit.parent
            and si.posting_date between "{from_date}" AND "{to_date}"
            and si.docstatus = 1
            and si.company = "{company}"
        GROUP BY sit.item_code
        ORDER BY sit.item_code,
            si.posting_date DESC
    ) sit1
    LEFT JOIN `tabItem` it ON it.item_code = sit1.item_code
    LEFT JOIN (
        SELECT ip.price_list_rate,
            max(ip.creation),
            ip.item_code AS item_code
        FROM `tabItem Price` ip
        WHERE ip.selling = 1
            AND ip.price_list = "Ret - Camo"
        GROUP BY ip.item_code
    ) AS ip1 ON ip1.item_code = sit1.item_code
    LEFT JOIN (
        SELECT parent,
            barcode,
            min(creation)
        FROM `tabItem Barcode` ib
        GROUP BY ib.parent
    ) AS ib1 ON ib1.parent = sit1.item_code
    LEFT JOIN (
        SELECT its.supplier_part_no,
            its.supplier,
            its.parent,
            min(its.creation)
        FROM `tabItem Supplier` its
        GROUP BY its.parent
    ) is1 ON is1.parent = sit1.item_code
    LEFT JOIN (
        SELECT pit.name,
            CONCAT(pi.posting_date, " ", pi.posting_time) AS last_pi_date,
            pit.rate,
            pit.item_code,
            max(pit.creation)
        FROM `tabPurchase Invoice Item` pit,
            `tabPurchase Invoice` pi
        WHERE pit.docstatus = 1
            AND pi.docstatus = 1
            AND pit.parent = pi.name
        GROUP BY item_code
    ) AS pit1 ON pit1.item_code = sit1.item_code
    LEFT JOIN (
        select bin.item_code,
            bin.warehouse,
            sum(bin.actual_qty) as actual_qty,
            sum(case when(bin.warehouse = "W01-WHS-Active Stock - ICL") then bin.actual_qty else 0 end) wh_whs,
            sum(case when(bin.warehouse = "R05-DTN-Active Stock - ICL") then bin.actual_qty else 0 end) wh_dtn,
            sum(case when(bin.warehouse = "R07-Queen-Active Stock - ICL") then bin.actual_qty else 0 end) wh_queen,
            sum(case when(bin.warehouse = "R06-AMB-Active Stock - ICL") then bin.actual_qty else 0 end) wh_amb,
            sum(case when(bin.warehouse = "R04-Mon-Active Stock - ICL") then bin.actual_qty else 0 end) wh_mon,
            sum(case when(bin.warehouse = "R03-Vic-Active Stock - ICL") then bin.actual_qty else 0 end) wh_vic,
            sum(case when(bin.warehouse = "R01-Gor-Active Stock - ICL") then bin.actual_qty else 0 end) wh_gor,
            sum(case when(bin.warehouse = "R02-Edm-Active Stock - ICL") then bin.actual_qty else 0 end) wh_edm
        from `tabBin` bin
        where bin.warehouse in (
            "W01-WHS-Active Stock - ICL",    
            "R05-DTN-Active Stock - ICL",
            "R07-Queen-Active Stock - ICL",
            "R06-AMB-Active Stock - ICL",
            "R04-Mon-Active Stock - ICL",
            "R03-Vic-Active Stock - ICL",
            "R01-Gor-Active Stock - ICL",
            "R02-Edm-Active Stock - ICL"
        )
        and bin.actual_qty > 0
        group by bin.item_code
    ) bin1 on bin1.item_code = sit1.item_code
    LEFT JOIN (
        select GROUP_CONCAT(DISTINCT mri.parent) as material_request,
        mri.item_code
        from `tabMaterial Request Item` mri
        where mri.docstatus = 1 and (mri.qty - mri.received_qty) > 0
        GROUP BY mri.item_code
    ) mri1 on mri1.item_code = sit1.item_code
    LEFT JOIN (
        SELECT
        poi.item_code,
        GROUP_CONCAT(
                DISTINCT CONCAT(
                    poi.parent,
                    "(",
                    (poi.qty - poi.received_qty) DIV 1,
                    ")",
                    "[",
                    poi.schedule_date,
                    "]"
                ) SEPARATOR ', '
        ) as expected_pos,
        GROUP_CONCAT(
                DISTINCT CONCAT(
                    poi.parent,
                    " ",
                    "(",
                    poi.schedule_date,
                    ")"
                ) SEPARATOR ', '
        ) as po_eta
        from `tabPurchase Order Item` poi
        where poi.docstatus = 1 and (poi.qty - poi.received_qty) > 0
        GROUP BY poi.item_code
    ) poi1 on poi1.item_code = sit1.item_code
    LEFT JOIN(
        SELECT GROUP_CONCAT(DISTINCT tl.tag SEPARATOR ', ') as tag, tl.parent from `tabTag Link` tl
        where tl.document_type = "Item"
        GROUP BY tl.parent
    ) tl1 ON tl1.parent = sit1.item_code;
        """.format(
            company=frappe.utils.get_defaults("company"),
            from_date=str(start_date),
            to_date=str(end_date),
        )
        self.data = frappe.db.sql(query, as_dict=1)
