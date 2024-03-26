# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.desk.reportview import build_match_conditions
from collections import defaultdict
from frappe.utils import getdate, nowdate
from dateutil.relativedelta import relativedelta
from datetime import timedelta, datetime
from operator import itemgetter
import requests

def execute(filters=None):
	if not filters:
		filters = {}

	conditions = get_conditions(filters)
	columns = get_column(filters,conditions)
	data = []

	master = get_master(conditions,filters)
	
	#Get US data
	us_data = {}
	us_data = get_us_data(filters)
	
	# details = get_details(conditions,filters)
	combo_dict = {}
	total = 0
	for i in master:
		row = {}
		row["ifw_retailskusuffix"] = i.get("ifw_retailskusuffix")
		row["item_name"] = i.get("item_name")
		row["item_code"] = i.get("item_code")

		row["ifw_duty_rate"] = i.get("ifw_duty_rate")
		row["ifw_discontinued"] = i.get("ifw_discontinued")
		row["ifw_product_name_ci"] = i.get("ifw_product_name_ci")
		row["ifw_item_notes"] = i.get("ifw_item_notes")
		row["ifw_item_notes2"] = i.get("ifw_item_notes2")
		row["ifw_po_notes"] = i.get("ifw_po_notes")
		row["ais_poreorderqty"] = i.get("ais_poreorderqty")
		row["ais_poreorderlevel"] = i.get("ais_poreorderlevel")
		row["country_of_origin"] = i.get("country_of_origin")
		row["customs_tariff_number"] = i.get("customs_tariff_number")

		row["supplier_sku"] = i.get("supplier_part_no")
		
		row["supplier_name"] = i.get("supplier")
		row["sqoh"] = i.get("ifw_supplier_qoh")
		
		row["barcode"] = frappe.db.get_value("Item Barcode", {"parent": i.get("item_code")}, "barcode")

		row["asi_item_class"] = i.get("asi_item_class")

		row["item_image"] =  "<a target="+str("_blank")+" href = "+str(i.get("image"))+"> "+str(i.get("image"))+" </a>"   

		row["rate"] = get_item_details(i.get("item_code"), "Selling")
		# row["item_discontinued"] = i.get("disabled")
		row["date_last_received"] = get_date_last_received(i.get("item_code"), i.get("supplier"))
		row["item_cost"] = get_item_details(i.get("item_code"), "Buying", i.get("supplier"))
		row["stock_uom"] = i.get("stock_uom")
		
		row["wh_whs"] = get_qty(i.get("item_code"), "W01-WHS-Active Stock - ICL") or 0
		row["wh_dtn"] = get_qty(i.get("item_code"), "R05-DTN-Active Stock - ICL") or 0
		row["wh_queen"] = get_qty(i.get("item_code"), "R07-Queen-Active Stock - ICL") or 0
		#row["wh_amb"] = get_qty(i.get("item_code"), "R06-AMB-Active Stock - ICL") or 0
		row["wh_mon"] = get_qty(i.get("item_code"), "R04-Mon-Active Stock - ICL") or 0
		row["wh_vic"] = get_qty(i.get("item_code"), "R03-Vic-Active Stock - ICL") or 0
		row["wh_edm"] = get_qty(i.get("item_code"), "R02-Edm-Active Stock - ICL") or 0
		row["wh_gor"] = get_qty(i.get("item_code"), "R01-Gor-Active Stock - ICL") or 0
		row["us_qoh"] = us_data.get(i.get("item_code")) or 0
		
		row["total_actual_qty"] = 0
		
		if row.get("wh_whs") > 0: 
			row["total_actual_qty"] += row.get("wh_whs")
		if row.get("wh_dtn") > 0:
			row["total_actual_qty"] += row.get("wh_dtn")
		if row.get("wh_queen") > 0:
			row["total_actual_qty"] += row.get("wh_queen")
		# if row.get("wh_amb") > 0:
		# 	row["total_actual_qty"] += row.get("wh_amb")
		if row.get("wh_mon") > 0:
			row["total_actual_qty"] += row.get("wh_mon")
		if row.get("wh_vic") > 0:
			row["total_actual_qty"] += row.get("wh_vic")
		if row.get("wh_edm") > 0:
			row["total_actual_qty"] += row.get("wh_edm")
		if row.get("wh_gor") > 0:
			row["total_actual_qty"] += row.get("wh_gor")
		warehouse = None if filters.get('reference_warehouse') == 'Total QOH' else filters.get('reference_warehouse')
		row["material_request"], row['mr_status'], row['mr_total_qty'] = get_open_material_request(i.get("item_code"), warehouse)
		row["tag"] = get_tags(i.get("item_code"))
		expected_pos = get_purchase_orders(i.get("item_code"), i.get("supplier"))
		row["expected_pos"] = expected_pos
		row["po_eta"] = get_last_purchase_orders(i.get("item_code"), i.get("supplier"))
		
		ordered_qty = get_open_po_qty(i.get("item_code"), i.get("supplier"), warehouse)
		row["ordered_qty"] = ordered_qty or 0.0
		row["last_sold_date"],row['olast_sold_date'] = get_date_last_sold(i.get("item_code"))
		sales_data = get_total_sold(i.get("item_code"))
		row["previous_year_sale"] = 0
		row["total"] = 0
		row["last_twelve_months"] = 0
		row["jrc_salerev"]=get_sales_rev(i.get("item_code"))
		today = getdate(nowdate())
		last_year = today.year-1
		current_year = today.year
		unique_customer_order = float(get_nocust12months(last_year, i.get("item_code")))
		beginvt = int(get_beginvt(i.get("item_code"), warehouse, today))
		row["jrc_nocust"]= unique_customer_order
		row["jrc_beginvt"] = beginvt
		row["jrc_endinvt"] = int(get_endinvt(i.get("item_code"), warehouse, today))
		row["jrc_invtor"] = float(get_invtor(i.get("item_code"), warehouse, today))
		row["jrc_lt"] = int(get_leadtime(i.get("item_code")))
		row["jrc_orderfreq"] = float(get_orderfreq(last_year, i.get("item_code")) or 0) /  (unique_customer_order or 1)
		row["jrc_avgorderqty"] = float(get_avgorderqty(last_year, i.get("item_code")) or 0) / 12
		row["jrc_puom"] = get_puom(i.get("item_code"))
		row["jrc_moo"] = get_moo(i.get("item_code"))
		row["jrc_ss"] = get_ss(i.get("item_code"))
		row["jrc_discountitem"] = float(get_discountitem(last_year, i.get("item_code")) or 0)
		row["jrc_templatesku"] =  get_templatesku(i.get("item_code"))
		row["jrc_mthsck"] = beginvt  / ((float(get_mthsck(i.get("item_code"), warehouse, today))) or 1) 
		row["jrc_gpdsales"] = get_gpdsales(i.get("item_code"))
		last_month = getdate(str(datetime(today.year-1, 1,1)))
		while last_month <= today:
			month = last_month.strftime("%B")
			row[frappe.scrub("sold"+month+str(last_month.year))]=0
			last_month = last_month + relativedelta(months=1)

		row["sold_last_ten_days"] = 0
		row["sold_last_thirty_days"] = 0
		row["sold_last_sixty_days"] = 0
		row["sold_online"] = 0
		row["sold_in_store"] = 0
		for d in sales_data:
			posting_date = getdate(d.get("posting_date"))
			qty = d.get("qty")
			month = posting_date.strftime("%B")
			if posting_date.year == last_year:
				row["previous_year_sale"] += qty
				row[frappe.scrub("sold"+month+str(posting_date.year))] += qty
			elif posting_date.year == current_year:
				row["total"] += qty
				row[frappe.scrub("sold"+month+str(posting_date.year))] += qty
			# if row.get(frappe.scrub("sold"+month+str(posting_date.year))):
			# 	row[frappe.scrub("sold"+month+str(posting_date.year))] += qty
			# row[frappe.scrub("soldjanuary2021")] += qty
			last12_month_date = today - relativedelta(years=1)
			if posting_date >= last12_month_date:
				row["last_twelve_months"] += qty
				#For sold online and in store
				if d.get("source") is not None and d.get("source") != "" and d.get('source').split()[0].strip() == "Website":
					row["sold_online"] += qty
				else:
					row["sold_in_store"] += qty

			sold_last_ten_days = today - timedelta(days=10)
			sold_last_thirty_days = today - timedelta(days=30)
			sold_last_sixty_days = today - timedelta(days=60)

			if posting_date >= sold_last_sixty_days:
				row["sold_last_sixty_days"] += qty
				if posting_date >= sold_last_thirty_days:
					row["sold_last_thirty_days"] += qty
					if posting_date >= sold_last_ten_days:
						row["sold_last_ten_days"] += qty
						
		#For Quantity to order
		reference_warehouse = get_reference_warehouse(filters)
		if row.get(reference_warehouse, 0) <= row.get("ais_poreorderlevel", 0):
			row["qty_to_order"] = row.get("ais_poreorderqty", 0)
		#Add material requests total and remove submitted purchase orders
		row["qty_to_order"] = row.get("qty_to_order", 0) + row.get("mr_total_qty", 0) - row.get("ordered_qty", 0)
		if row["qty_to_order"] < 0:
			row["qty_to_order"] = 0
		row["gdp_price"] = frappe.db.get_value("Item Price", {"price_list": "RET - GPD", "selling": 1, 
								"item_code": i.get("item_code")}, "price_list_rate")
		data.append(row)
	data = sorted(data, key=itemgetter("olast_sold_date"), reverse=True)

	return columns, data

def get_reference_warehouse(filters):
	warehouse = filters.get('reference_warehouse')
	warehouse_map = {
		"Total QOH": "total_actual_qty",
		"W01-WHS-Active Stock - ICL": "wh_whs",
		"R05-DTN-Active Stock - ICL": "wh_dtn",
		"R07-Queen-Active Stock - ICL": "wh_queen",
		#"R06-AMB-Active Stock - ICL": "wh_amb",
		"R04-Mon-Active Stock - ICL": "wh_mon",
		"R03-Vic-Active Stock - ICL": "wh_vic",
		"R02-Edm-Active Stock - ICL": "wh_edm",
		"R01-Gor-Active Stock - ICL": "wh_gor"
	}
	return warehouse_map.get(warehouse)

def get_column(filters,conditions):
	columns = [
			{
				"label": _("RetailSkuSuffix"),
				"fieldname": "ifw_retailskusuffix",
				"fieldtype": "Data",
				"width": 150,
			},
			{
				"label": "QtyToOrderd",
				"fieldname": "qty_to_order",
				"fieldtype": "Float",
				"width": 150
			},
			{
				"label": "DollarAmount",
				"fieldname": "dollar_amount",
				"fieldtype": "Float",
				"width": 150
			},
			{
				"label": "ERPNextItemCode",
				"options": "Item",
				"fieldname": "item_code",
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
				"label": _("ItemClass"),
				"fieldname": "asi_item_class",
				"fieldtype": "Data",
				"width": 150,
				"align": "left",
			},
			{
				"label": _("ItemName"),
				"fieldname": "item_name",
				"fieldtype": "Data",
				"width": 300,
			},

			{
				"label": _("ItemImage"),
				"fieldname": "item_image",
				"fieldtype": "Data",
				"width": 200,
			},
			{
				"label": _("Duty rate"),
				"fieldname": "ifw_duty_rate",
				"fieldtype": "Int",
				"width": 100,
			},
			{
				"label": _("Discontinued"),
				"fieldname": "ifw_discontinued",
				"fieldtype": "Check",
				"width": 100,
			},
			{
				"label": _("ProductNameCI"),
				"fieldname": "ifw_product_name_ci",
				"fieldtype": "Data",
				"width": 100,
			},
			
			{
				"label": _("Item Notes"),
				"fieldname": "ifw_item_notes",
				"fieldtype": "Data",
				"width": 100,
			},
			{
				"label": _("Item Notes2"),
				"fieldname": "ifw_item_notes2",
				"fieldtype": "Data",
				"width": 100,
			},
			{
				"label": _("PONotes"),
				"fieldname": "ifw_po_notes",
				"fieldtype": "Data",
				"width": 100,
			},
			{
				"label": _("POReorderLevel"),
				"fieldname": "ais_poreorderlevel",
				"fieldtype": "Int",
				"width": 100,
			},
			{
				"label": _("POReorderQty"),
				"fieldname": "ais_poreorderqty",
				"fieldtype": "Int",
				"width": 100,
			},
			{
				"label": _("Country of Origin"),
				"fieldname": "country_of_origin",
				"fieldtype": "Link",
				"options": "Country",
				"width": 100,
			},
			{
				"label": _("HS Code"),
				"fieldname": "customs_tariff_number",
				"fieldtype": "Link",
				"options": "Customs Tariff Number",
				"width": 100,
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
				"label": "GDP Price",
				"fieldname": "gdp_price",
				"fieldtype": "Currency",
				"width": 140 	
			},
			# {
			# 	"label": _("Discointinued"),
			# 	"fieldname": "item_discontinued",
			# 	"fieldtype": "Boolean",
			# 	"width": 100,
			# 	"default": False,
			# },
			# {
			# 	"label": _("ETA"),
			# 	"fieldname": "eta",
			# 	"fieldtype": "Date",
			# 	"width": 100,
			# },
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
				"label": _("SQOH"),
				"fieldname": "sqoh",
				"fieldtype": "Float",
				"width": 100,
			},
			{
				"label": _("UOM"),
				"fieldname": "stock_uom",
				"fieldtype": "Data",
				"width": 100,
			}
		]
		
	if filters.get('reference_warehouse') != 'Total QOH':
		columns.append(
			{
				"label": _(filters.get("reference_warehouse")),
				"fieldname": get_reference_warehouse(filters),
				"fieldtype": "Int",
				"width": 200
			}
		)
	else:
		columns.extend([
			{
				"label": _("W01-WHS-Active Stock - ICL"),
				"fieldname": "wh_whs",
				"fieldtype": "Int",
				"width": 200,
			},
			{
				"label": _("R05-DTN-Active Stock - ICL"),
				"fieldname": "wh_dtn",
				"fieldtype": "Int",
				"width": 200,
			},
			{
				"label": _("R07-Queen-Active Stock - ICL"),
				"fieldname": "wh_queen",
				"fieldtype": "Int",
				"width": 200,
			},
			# {
			# 	"label": _("R06-AMB-Active Stock - ICL"),
			# 	"fieldname": "wh_amb",
			# 	"fieldtype": "Int",
			# 	"width": 200,
			# },
			{
				"label": _("R04-Mon-Active Stock - ICL"),
				"fieldname": "wh_mon",
				"fieldtype": "Int",
				"width": 200,
			},
			{
				"label": _("R03-Vic-Active Stock - ICL"),
				"fieldname": "wh_vic",
				"fieldtype": "Int",
				"width": 200,
			},
			{
				"label": _("R02-Edm-Active Stock - ICL"),
				"fieldname": "wh_edm",
				"fieldtype": "Int",
				"width": 200,
			},
			{
				"label": _("R01-Gor-Active Stock - ICL"),
				"fieldname": "wh_gor",
				"fieldtype": "Int",
				"width": 200,
			}
		])
		
	columns.extend([
		{
			"label": _("TotalQOH"),
			"fieldname": "total_actual_qty",
			"fieldtype": "Int",
			"width": 140,
		},
		{
			"label": _("US QOH"),
			"fieldname": "us_qoh",
			"fieldtype": "Int",
			"width": 200
		},
		{
			"label": _("Material Request"),
			"fieldname": "material_request",
			"fieldtype": "Data",
			"width": 200,
		},
		{
			"label": _("Material Request Status"),
			"fieldname": "mr_status",
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
			"label": _("OrderedQty"),
			"fieldname": "ordered_qty",
			"fieldtype": "Int",
			"width": 120,
		},
		{
			"label": _("PreviousYSale"),
			"fieldname": "previous_year_sale",
			"fieldtype": "Int",
			"width": 140,
		},
		{
			"label": _("CurrentYearSales"),
			"fieldname": "total",
			"fieldtype": "Int",
			"width": 140,
		},
		{
			"label": _("TotalSold12Months"),
			"fieldname": "last_twelve_months",
			"fieldtype": "Int",
			"width": 140,
		},
		{
			"label": _("OnlineSold12Months"),
			"fieldname": "sold_online",
			"fieldtype": "Int",
			"width": 140,
		},
		{
			"label": _("StoreSold12Months"),
			"fieldname": "sold_in_store",
			"fieldtype": "Int",
			"width": 140,
		}
	])
	today = getdate(nowdate())
	last_month = getdate(str(datetime(today.year-1, today.month,1)))
	while last_month <= today:
		month = last_month.strftime("%B")
		columns.append({
        		"label": _(str(last_month.year) + "_Sold" + month),
                "fieldname": frappe.scrub("sold"+month+str(last_month.year)),
                "fieldtype": "Int",
                "width": 140,
		})
		last_month = last_month + relativedelta(months=1)

	columns.extend([
    	{
            "label": _("SoldLast10Days"),
            "fieldname": "sold_last_ten_days",
            "fieldtype": "Int",
            "width": 140,
        },
        {
            "label": _("SoldLast30Days"),
            "fieldname": "sold_last_thirty_days",
            "fieldtype": "Int",
            "width": 140,
        },
        {
            "label": _("SoldLast60Days"),
            "fieldname": "sold_last_sixty_days",
            "fieldtype": "Int",
            "width": 140,
            "default": False,
        },
        {
            "label": _("DateLastSold"),
            "fieldname": "last_sold_date",
            "fieldtype": "Data",
            "width": 100,
		},
		{
            "label": _("SalesRev"),
            "fieldname": "jrc_salerev",
            "fieldtype": "Currency",
            "width": 100,
		},
		{
            "label": _("NoCustL12M"),
            "fieldname": "jrc_nocust",
            "fieldtype": "Int",
            "width": 100,
		},
		{
            "label": _("BegIvnt"),
            "fieldname": "jrc_beginvt",
            "fieldtype": "Int",
            "width": 100,
		},
		{
            "label": _("EndInvt"),
            "fieldname": "jrc_endinvt",
            "fieldtype": "Int",
            "width": 100,
		},
		{
            "label": _("InvTOV"),
            "fieldname": "jrc_invtor",
            "fieldtype": "Float",
            "width": 100,
		},
		{
            "label": _("LT"),
            "fieldname": "jrc_lt",
            "fieldtype": "Float",
            "width": 100,
		},
		{
            "label": _("OrderFreq12M"),
            "fieldname": "jrc_orderfreq",
            "fieldtype": "Float",
            "width": 100,
		},
		{
            "label": _("AvgOrderQty"),
            "fieldname": "jrc_avgorderqty",
            "fieldtype": "Float",
            "width": 100,
		},
		{
            "label": _("PUOM"),
            "fieldname": "jrc_puom",
            "fieldtype": "Data",
            "width": 100,
		},
		{
            "label": _("MOO"),
            "fieldname": "jrc_moo",
            "fieldtype": "Data",
            "width": 100,
		},
		{
            "label": _("SS"),
            "fieldname": "jrc_ss",
            "fieldtype": "Data",
            "width": 100,
		},
		{
            "label": _("DiscountPer12M"),
            "fieldname": "jrc_discountitem",
            "fieldtype": "Float",
            "width": 100,
		},
		{
            "label": _("Temp. SKU"),
            "fieldname": "jrc_templatesku",
            "fieldtype": "Data",
            "width": 100,
		},
		{
            "label": _("MthStck"),
            "fieldname": "jrc_mthsck",
            "fieldtype": "Float",
            "width": 100,
		},
		{
            "label": _("GPDSales"),
            "fieldname": "jrc_gpdsales",
            "fieldtype": "Float",
            "width": 100,
		}
	])
	return columns

def get_gpdsales(item_code):

	data =  frappe.db.sql("""
		SELECT SUM(`tabSales Invoice Item`.stock_qty) as total from `tabSales Invoice Item`
		Inner join `tabSales Invoice` on `tabSales Invoice Item`.parent = `tabSales Invoice`.name
		where `tabSales Invoice`.status ="Paid" and `tabSales Invoice Item`.item_code =%s and `tabSales Invoice`.source = 'Website - GPD'
	""", (item_code), as_dict=1)
	gpdsales = 0
	if data[0].total:
		gpdsales = data[0].total
	return gpdsales

def get_mthsck(item_code, warehouse, today):
	fromdate = str(today.year)+"-"+str(today.month)+"-01"
	enddate = str(today.year)+"-"+str(today.month)+"-30"

	data =  frappe.db.sql("""
		SELECT SUM(`tabSales Invoice Item`.stock_qty) as total from `tabSales Invoice Item`
		Inner join `tabSales Invoice` on `tabSales Invoice Item`.parent = `tabSales Invoice`.name
		where `tabSales Invoice`.status ="Paid" and `tabSales Invoice Item`.item_code =%s and `tabSales Invoice`.posting_date BETWEEN %s and %s
	""", (item_code, fromdate , enddate), as_dict=1)
	tqoh = 0
	if data[0].total:
		tqoh = data[0].total
	return tqoh
def get_templatesku(item_code):
	data =  frappe.db.sql(""" SELECT variant_of from `tabItem` where name =%s """,item_code, as_dict=1)

	return data[0].variant_of

def get_discountitem(last_year, item_code):
	data =  frappe.db.sql("""
		SELECT count(DISTINCT(`tabSales Invoice`.name))as total from `tabSales Invoice Item`
		Inner join `tabSales Invoice` on `tabSales Invoice Item`.parent = `tabSales Invoice`.name
		where `tabSales Invoice`.status ="Paid" and `tabSales Invoice Item`.discount_amount > 0 and `tabSales Invoice Item`.item_code =%s and `tabSales Invoice`.posting_date BETWEEN %s and %s
	""", (item_code, str(last_year)+"-01-01",str(last_year)+"-12-30"), as_dict=1)

	return data[0].total
def get_ss(item_code):
	data =  frappe.db.sql(""" SELECT safety_stock from `tabItem` where name =%s """,item_code, as_dict=1)

	return data[0].safety_stock

def get_moo(item_code):
	data =  frappe.db.sql(""" SELECT min_order_qty from `tabItem` where name =%s """,item_code, as_dict=1)

	return data[0].min_order_qty

def get_puom(item_code):
	data =  frappe.db.sql(""" SELECT purchase_uom from `tabItem` where name =%s """,item_code, as_dict=1)

	return data[0].purchase_uom

def get_avgorderqty(last_year, item_code):
	data =  frappe.db.sql("""
		SELECT SUM(`tabPurchase Receipt Item`.received_qty) as total from `tabPurchase Receipt Item`
		Inner join `tabPurchase Receipt` on `tabPurchase Receipt Item`.parent = `tabPurchase Receipt`.name
		where `tabPurchase Receipt`.docstatus =1 and `tabPurchase Receipt Item`.item_code =%s and `tabPurchase Receipt`.posting_date BETWEEN %s and %s
	""", (item_code, str(last_year)+"-01-01",str(last_year)+"-12-30"), as_dict=1)

	return data[0].total
def get_orderfreq(last_year, item_code):
	data =  frappe.db.sql("""
		SELECT sum(`tabSales Invoice Item`.stock_qty) as total from `tabSales Invoice Item`
		Inner join `tabSales Invoice` on `tabSales Invoice Item`.parent = `tabSales Invoice`.name
		where `tabSales Invoice`.status ="Paid" and `tabSales Invoice Item`.item_code =%s and `tabSales Invoice`.posting_date BETWEEN %s and %s
	""", (item_code, str(last_year)+"-01-01",str(last_year)+"-12-30"), as_dict=1)

	return data[0].total

def get_leadtime(item_code):
	data = frappe.db.sql("SELECT lead_time_days FROM `tabItem` where name =%s",item_code, as_dict=1)
	lead_time_days = 0
	if data[0].lead_time_days:
		lead_time_days = data[0].lead_time_days

	return lead_time_days

def get_endinvt(item_code, warehouse, today):
	lastmonth = today.month - 1
	fromdate = str(today.year)+"-"+str(lastmonth)+"-01"
	enddate = str(today.year)+"-"+str(lastmonth)+"-30"

	data = frappe.db.sql("""
		Select sum(actual_qty) as total from `tabStock Ledger Entry`
		where item_code =%s and posting_date between %s and %s 
	""",(item_code, fromdate, enddate), as_dict=1)
	total = 0
	if data[0].total:
		total = data[0].total
	return total

def get_beginvt(item_code, warehouse, today):
	fromdate = str(today.year)+"-"+str(today.month)+"-01"
	enddate = str(today.year)+"-"+str(today.month)+"-30"

	data = frappe.db.sql("""
		Select sum(actual_qty) as total from `tabStock Ledger Entry`
		where item_code =%s and posting_date between %s and %s 
	""",(item_code, fromdate, enddate), as_dict=1)
	total = 0
	if data[0].total:
		total = data[0].total
	return total

def get_invtor(item_code, warehouse, today):
	fromdate = str(today.year)+"-"+str(today.month)+"-01"
	enddate = str(today.year)+"-"+str(today.month)+"-30"

	prev_fromdate = str(today.year)+"-"+str(today.month - 1)+"-01"
	prev_enddate = str(today.year)+"-"+str(today.month - 1)+"-30"

	current = frappe.db.sql("""
		Select sum(stock_value_difference) as total from `tabStock Ledger Entry`
		where item_code =%s  and posting_date between %s and %s 
	""",(item_code,  fromdate, enddate), as_dict=1)

	prev = frappe.db.sql("""
		Select sum(stock_value_difference) as total from `tabStock Ledger Entry`
		where item_code =%s  and posting_date between %s and %s 
	""",(item_code, prev_fromdate, prev_enddate), as_dict=1)
	
	total = 0
	current_month = 0
	prev_month = 0
	total_invor = 0
	if current[0].total:
		current_month = current[0].total

	if prev[0].total:
		prev_month = prev[0].total 
	
	if current_month and prev_month:
		total_invor = float(current_month) / (float(prev_month) / 2)

	if total_invor:
		total = total_invor
	return total

def get_master(conditions="", filters={}):
	data = frappe.db.sql("""
			select  
				i.ifw_retailskusuffix, i.item_code, i.item_name, i.image,
				i.asi_item_class, s.supplier, s.supplier_part_no, i.disabled, 
				country_of_origin,customs_tariff_number, ifw_duty_rate,
				ifw_discontinued,ifw_product_name_ci,ifw_item_notes,ifw_item_notes2,
				ifw_po_notes, ais_poreorderqty, ais_poreorderlevel, 
				s.ifw_supplier_qoh, i.stock_uom
			from 
				`tabItem Supplier` s 
			inner join 
				`tabItem` i on i.name = s.parent
			where 1 = 1 %s
		"""%(conditions), filters, as_dict=1)
	return data

def get_conditions(filters):
	conditions = ""
	suppliers = []
	limit = filters.get("limit")
	if filters.get('supplier'):
		suppliers = frappe.parse_json(filters.get("supplier"))
		suppliers.append("asa")
		suppliers.append("asaa")
		# format_strings = ','.join(['%s'] * len(suppliers))
		conditions += " and s.supplier IN %(supplier)s"
	if limit != "All":
		conditions += " limit {}".format(str(limit))
	return conditions

def get_date_last_received(item, supplier):
	date = None
	data= frappe.db.sql("""select 
							max(transaction_date) 
						from `tabPurchase Order` p 
						inner join 
							`tabPurchase Order Item` c on p.name = c.parent 
						where 
							c.item_code = %s and p.docstatus = 1
							and (c.warehouse IS NULL OR c.warehouse <> 'US02-Houston - Active Stock - ICL')
		""",(item))
	if data:
		date = data[0][0]
	if date:
		date = getdate(date)
		date = date.strftime("%d-%b-%Y")
	return date

def get_sales_rev(item_code):
	data =  frappe.db.sql("""
		SELECT sum(amount) as total from `tabSales Invoice Item`
		Inner join `tabSales Invoice` on `tabSales Invoice Item`.parent = `tabSales Invoice`.name
		where `tabSales Invoice`.status ="Paid" and `tabSales Invoice Item`.item_code =%s
	""", item_code, as_dict=1)

	return data[0].total

def get_nocust12months(last_year, item_code):
	data =  frappe.db.sql("""
		SELECT count(DISTINCT(`tabSales Invoice`.customer)) as total from `tabSales Invoice Item`
		Inner join `tabSales Invoice` on `tabSales Invoice Item`.parent = `tabSales Invoice`.name
		where `tabSales Invoice`.status ="Paid" and `tabSales Invoice Item`.item_code =%s and `tabSales Invoice`.posting_date BETWEEN %s and %s
	""", (item_code, str(last_year)+"-01-01",str(last_year)+"-12-30"), as_dict=1)

	return data[0].total

def get_date_last_sold(item):
	rdate = None
	date = None
	data= frappe.db.sql("""select 
							max(posting_date) 
						from 
							`tabSales Invoice` p 
						inner join 
							`tabSales Invoice Item` c on p.name = c.parent 
						left join
								`tabAddress` address on address.name = p.customer_address
						where 
							c.item_code = %s and p.docstatus = 1
							and (c.warehouse IS NULL OR c.warehouse <> 'US02-Houston - Active Stock - ICL')
		""",(item))
	if data:
		date = data[0][0]
	if date:
		date = getdate(date)
		rdate = date.strftime("%d-%b-%Y")
	else:
		date = getdate('1930-01-01')
	return rdate, date

def get_total_sold(item):
	data= frappe.db.sql("""select 
							p.posting_date, c.qty, p.source
						from 
							`tabSales Invoice Item` c 
						left join
							`tabSales Invoice` p on p.name = c.parent 
						where 
							c.item_code = %s and p.docstatus = 1
							and (c.warehouse IS NULL OR c.warehouse <> 'US02-Houston - Active Stock - ICL')
						ORDER BY p.posting_date DESC
		""",(item), as_dict=1)
	return data

def get_qty(item, warehouse):
	qty = 0
	data= frappe.db.sql("""select actual_qty-reserved_qty AS qty from `tabBin`
		where item_code = %s and warehouse=%s
		""",(item,warehouse), as_dict=1)
	if data and data[0]['qty'] > 0:
		qty = data[0]['qty']
	return qty

def get_open_material_request(item, warehouse=None):
	material_requests = ''
	mr_status = ''
	total_qty = 0
	where = ''
	if warehouse is not None:
		where = " AND warehouse = '{}'".format(warehouse)
	data = frappe.db.sql("""select p.name, c.qty, p.status from `tabMaterial Request` p inner join 
		`tabMaterial Request Item` c on c.parent = p.name where p.docstatus=1 and c.item_code = %s
		and p.status IN ('Pending', 'Partially Ordered')""" + where,(item))
	for d in data:
		material_requests += d[0]+" ("+str(d[1])+")" if material_requests == '' else ", " + d[0]+" ("+str(d[1])+")"
		mr_status += d[2] if mr_status == '' else ', ' + d[2]
		total_qty = total_qty + d[1]
	return material_requests, mr_status, total_qty

def get_tags(item):
	output = ""
	data = frappe.db.sql("""select tag from `tabTag Link` where document_type='Item' and document_name = %s""",(item))
	for d in data:
		output += d[0]+", "
	return output

def get_purchase_orders(item,supplier):
	output = ""
	data = frappe.db.sql("""select 
								p.name, c.qty-c.received_qty, p.eta_date 
							from 
								`tabPurchase Order` p 
							inner join 
								`tabPurchase Order Item` c on p.name = c.parent 
							where 
								p.docstatus=1 and c.item_code = %s and c.received_qty < c.qty 
								and p.status in ("To Receive and Bill", "To Receive")
								and p.supplier = %s and c.warehouse <> 'US02-Houston - Active Stock - ICL'""",
						(item, supplier))
	for d in data:
		name = get_pr_draft(item, d[0])
		qty = get_pr_qty(item, d[0])
		draft_output = ""
		for n in name:
			if n[1]>0:
				draft_output += n[0] + "("+str(n[1]) +"), | "
			#frappe.throw(frappe.as_json(draft_output))
		# if qty > 0:
		# 	frappe.throw(frappe.as_json(name[0][1]))
		# 	output += name + "("+str(qty) +"),"
		if not draft_output:
			output += d[0]+" ("+str(d[1])+"), | "	
		else:
			output += draft_output
	return output

def get_last_purchase_orders(item,supplier):
	output = ""
	data = frappe.db.sql("""select 
								p.name, c.qty-c.received_qty, p.eta_date 
							from 
								`tabPurchase Order` p 
							inner join 
								`tabPurchase Order Item` c on p.name = c.parent 
							where 
								p.docstatus=1 and c.item_code = %s and c.received_qty < c.qty 
								and p.status in ("To Receive and Bill", "To Receive") and
								p.supplier = %s and c.warehouse <> 'US02-Houston - Active Stock - ICL'""",
				(item, supplier))
	for d in data:
		output += d[0]+" ("+str(getdate(d[2]).strftime("%d-%b-%Y"))+"), | "
		# output = d[0]+" ("+str(d[1])+")"
	return output

def get_pr_draft( item, po_name):
	output = ""
	data = frappe.db.sql("""select 
								pr.name, ri.qty 
							from 
								`tabPurchase Receipt` pr 
							inner join 
								`tabPurchase Receipt Item` ri on  pr.name = ri.parent	
							where 
								pr.docstatus=0 and ri.item_code = %s and pr.purchase_order = %s
								and ri.warehouse <> 'US02-Houston - Active Stock - ICL'""",(item, po_name))
	for d in data:
		output += d[0]+" ("+str(d[1])+"), "	
	return data

def get_pr_qty( item, po_name):
	qty = 0
	data = frappe.db.sql("""select 
								ri.qty 
							from 
								`tabPurchase Receipt` pr 
							inner join 
								`tabPurchase Receipt Item` ri on  pr.name = ri.parent
							where 
								pr.docstatus=0 and ri.item_code = %s and pr.purchase_order = %s
								and ri.warehouse <> 'US02-Houston - Active Stock - ICL'""",(item, po_name))
	for d in data:
		qty = d[0]
	return qty

def get_open_po_qty(item,supplier, warehouse=None):
	where = ''
	if warehouse is not None:
		where = " AND c.warehouse = '{}'".format(warehouse)
	output = ""
	data = frappe.db.sql("""select 
								SUM(c.qty) - SUM(c.received_qty) 
							from 
								`tabPurchase Order` p 
							inner join 
								`tabPurchase Order Item` c on p.name = c.parent 
							where 
								p.docstatus=1 and c.item_code = %s and c.received_qty < c.qty 
								and  p.status in ("To Receive and Bill", "To Receive")
								and c.warehouse <> 'US02-Houston - Active Stock - ICL'
							""" + where, 
						(item))
	if data:
		return data[0][0]
	return 0

@frappe.whitelist()
def get_item_details(item, list_type="Selling", supplier=None):
	price_list = frappe.db.get_value("Stock Settings", "Stock Settings", "ais_default_price_list")
	if price_list is None or price_list  == "":
		frappe.throw("Please set a default price list in stock Settings")
	cond = "and price_list = '{}' and selling = 1".format(price_list)
	if list_type == "Buying": cond= " and buying = 1"
	rate = 0
	date = frappe.utils.nowdate()
	r = frappe.db.sql("select price_list_rate from `tabItem Price` \
						where '{}' between valid_from and valid_upto and item_code = '{}' \
						{} limit 1".format(date, item, cond))
	if r:
		if r[0][0]:
			rate = r[0][0]
	else:
		r = frappe.db.sql("select price_list_rate from `tabItem Price` \
							where (valid_from <= '{}' or valid_upto >= '{}') and item_code = '{}' \
							{} limit 1".format(date, date, item, cond))
		if r:
			if r[0][0]:
				rate = r[0][0]
		else:
			r = frappe.db.sql("select price_list_rate from `tabItem Price` \
								where valid_from IS NULL and valid_upto IS NULL and item_code = '{}' \
								{} limit 1".format(item, cond))
			if r:
				if r[0][0]:
					rate = r[0][0]
	return rate

def test():
	today = getdate(nowdate())
	last_month = getdate(str(datetime(today.year-1, 1,1)))
	print(last_month.year)
	print(today.year)
	while last_month < today:
		month = last_month.strftime("%B")
		print(last_month.month)
		print(last_month.year)
		last_month = last_month + relativedelta(months=1)

def get_us_data(filters):
	item_search_settings = frappe.get_doc("Item Search Settings")
	if item_search_settings.get("sales_report_url") is not None and item_search_settings.get("sales_report_url") != "":
		us_request = requests.get(item_search_settings.get("sales_report_url"), 
						auth=(item_search_settings.api_key, item_search_settings.api_secret),
									params=filters)
		if us_request.status_code == 200:
			return us_request.json().get("message", {})
	else:
		return {}
