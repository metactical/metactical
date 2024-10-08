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
from frappe.desk.query_report import generate_report_result, get_report_doc
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
		warehouse = None if filters.get('reference_warehouse') == 'Total QOH' else filters.get('reference_warehouse')

		row["ifw_retailskusuffix"] = i.get("ifw_retailskusuffix")
		row["item_name"] = i.get("item_name")
		item_groups = get_item_group_parents(i.get("item_group"))
		row["itemgroups"] = item_groups
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
		if row.get("wh_vic") > 0:
			row["total_actual_qty"] += row.get("wh_vic")
		if row.get("wh_edm") > 0:
			row["total_actual_qty"] += row.get("wh_edm")
		if row.get("wh_gor") > 0:
			row["total_actual_qty"] += row.get("wh_gor")

		row["material_request"], row['mr_status'], row['mr_total_qty'] = get_open_material_request(i.get("item_code"), warehouse)
		row["tag"] = get_tags(i.get("item_code"))
		expected_pos = get_purchase_orders(i.get("item_code"), i.get("supplier"))
		row["expected_pos"] = expected_pos
		row["po_eta"] = get_last_purchase_orders(i.get("item_code"), i.get("supplier"))
		
		ordered_qty = get_open_po_qty(i.get("item_code"), i.get("supplier"), warehouse)
		row["ordered_qty"] = ordered_qty or 0.0
		row["last_sold_date"], row['olast_sold_date'] = get_date_last_sold(i.get("item_code"))

		sales_data = get_total_sold(i.get("item_code"))

		row["previous_year_sale"] = 0
		row["total"] = 0
		row["last_twelve_months"] = 0
		row["last_24_months"] = 0

		today = getdate(nowdate())

		years_to_subtract = 1
		if filters.get("sales_data_period") == '12':
			years_to_subtract = 1
		elif filters.get("sales_data_period") == '24':
			years_to_subtract = 2

		last_year = today.year-1
		current_year = today.year

		last_month = getdate(str(datetime(today.year-years_to_subtract, 1,1)))
		while last_month <= today:
			month = last_month.strftime("%B").lower()	
			row[frappe.scrub("sold"+month+str(last_month.year))]=0
			last_month = last_month + relativedelta(months=1)

		row["sold_last_ten_days"] = 0
		row["sold_last_thirty_days"] = 0
		row["sold_last_sixty_days"] = 0
		row["sold_online"] = 0
		row["sold_in_store"] = 0

		years_ago = today - relativedelta(years=years_to_subtract)
		for d in sales_data:
			posting_date = getdate(d.get("posting_date"))
			qty = d.get("qty")
			month = posting_date.strftime("%B")
			
			if posting_date.year == last_year:
				row["previous_year_sale"] += qty
			elif posting_date.year == current_year:
				row["total"] += qty

			last12_month_date = today - relativedelta(years=1)
			last24_month_date = today - relativedelta(years=2)
			if posting_date >= last12_month_date:
				row["last_twelve_months"] += qty
			
			if posting_date >= last24_month_date:
				row["last_24_months"] += qty
			
			if posting_date >= years_ago:
				row[frappe.scrub("sold"+month+str(posting_date.year))] += qty
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

		# sales revenue last 12/24 months
		years_before = getdate(str(datetime(today.year-years_to_subtract, today.month, today.day)))
		row["sales_revenue_last_twelve_months"] = get_sold_amount_in_dollars(i.get("item_code"), years_before)

		# no of customers bought an item in the last 12 months
		customers_12, customers_24 = get_unique_customers_bought_an_item(i.get("item_code"), today)
		row["no_cust_l12m"] = customers_12
		row["no_cust_l24m"] = customers_24

		# beginning and ending inventory
		row["beginning_inventory"], row["ending_inventory"] = get_inventory(i.get("item_code"), warehouse)

		# inventory turnover	
		# # get january 1st of the year
		start_date = getdate(str(datetime(today.year, 1, 1)))	
		row["inventory_turnover"] = (get_inventory_turnover(row["beginning_inventory"], row["ending_inventory"], start_date, sales_data)) * 100 / 100

		row["lead_time_in_days"] = frappe.db.get_value("Supplier", i.get("supplier"), "lead_time_in_days")

		# order frequencies
		order_frqs, ordered_quantities = get_order_frequency(i.get("item_code"), today)
		row["average_order_frequency_12"] = order_frqs["12"]
		row["average_order_frequency_24"] = order_frqs["24"]

		
		# remove the biggest and smallest values from the list 
		# if the biggest and smallest values appear more than once, remove only one of them
		# calucuation is based on months that have order only
		if len(ordered_quantities) <= 2:
			row["average_order_qty_last_twelve_months"] = 0
		elif len(ordered_quantities) > 2:
			ordered_quantities = sorted(ordered_quantities)
			ordered_quantities = ordered_quantities[1:-1]
			row["average_order_qty_last_twelve_months"] = round(sum(ordered_quantities)/len(ordered_quantities), 0) 
		
		discount_percentages = get_discount_percentages(i.get("item_code"), years_before)
		row["average_discount_last_twelve_months"] = sum(discount_percentages) / len(discount_percentages) if len(discount_percentages) > 0 else 0
		
		gpd_sales = get_gpd_sales(i.get("item_code"), years_before)
		row["gpd_sales_qty"] = gpd_sales[1]
		row["gpd_sales_amount"] = gpd_sales[0]
		row["purchase_uom"] = i.get("purchase_uom")
		row["minimum_order_qty"] = i.get("min_order_qty")
		row["safety_stock"] = i.get("safety_stock")
		row["erpnext_template"] = i.get("variant_of")

		# motnhly stock
		average_monthly_consumption_12, average_monthly_consumption_24 = get_monthly_consumption(i.get("item_code"), i.get("creation"), filters, sales_data)
		row["monthly_stock_12m"] = (((row["total_actual_qty"] + row["us_qoh"])/average_monthly_consumption_12) if average_monthly_consumption_12 > 0 else row["total_actual_qty"] + row["us_qoh"]) * 100 / 100
		row["monthly_stock_24m"] = (((row["total_actual_qty"] + row["us_qoh"])/average_monthly_consumption_24) if average_monthly_consumption_24 > 0 else row["total_actual_qty"] + row["us_qoh"]) * 100 / 100

		# NoStockOut12M
		row["no_stock_out_12m"] = get_stock_out_days(i.get("item_code"), years_before, filters)

		# suggested quantity to order
		row["ais_poreorderqty"] = i.get("ais_poreorderqty")
		row["ais_poreorderlevel"] = i.get("ais_poreorderlevel")

		# total lifetime sold quantity
		row["total_lifetime_sold"] = get_total_lifetime_sold(sales_data)

		data.append(row)

	data = sorted(data, key=itemgetter("olast_sold_date"), reverse=True)

	return columns, data

def get_inventory_turnover(beginning_inventory, ending_inventory, start_date, sales_data):
	average_inventory = (beginning_inventory + ending_inventory) / 2

	total = 0
	for d in sales_data:
		if d.get("posting_date") >= start_date:
			total += d.get("net_amount")

	return ((total / average_inventory) if average_inventory > 0 else 0 ) * 100 / 100

def get_stock_out_days(item_code, years_before, filters):
	warehouse_filter = ""
	if filters.get('reference_warehouse') != 'Total QOH':
		warehouse_filter = " and warehouse = '%s'"%(filters.get('reference_warehouse'))
	else:
		warehouse_filter = " and warehouse <> 'US02-Houston - Active Stock - ICL'"

	stock_out_days = frappe.db.sql("""
		select 
			warehouse, posting_date, qty_after_transaction
		from 
			`tabStock Ledger Entry`
		where
			item_code = '%s' and 
			posting_date >= '%s' and
			qty_after_transaction = 0
			%s
		order by 
			posting_date desc
	"""%(item_code, years_before, warehouse_filter), as_dict=1)

	total_stock_outs = 0
	stock_out_group_in_warehouse = {} # format will be like this {'W01-WHS-Active Stock - ICL': ['2023-01-09'], 'R05-DTN-Active Stock - ICL': ['2023-01-09']} ...

	if stock_out_days:
		for d in stock_out_days:
			date = d.get("posting_date").strftime("%Y-%m-%d")

			if date not in stock_out_group_in_warehouse:
				stock_out_group_in_warehouse[d.get("warehouse")] = []
			stock_out_group_in_warehouse[d.get("warehouse")].append(date)

		for warehouse, dates in stock_out_group_in_warehouse.items():
			for date in dates:
				if filters.get('reference_warehouse') == 'Total QOH':
					if has_stock_out(date, warehouse, item_code):
						total_stock_outs += 1
				else:
					total_stock_outs += 1

	return total_stock_outs

def has_stock_out(date, warehouse, item_code):
	# check if the item has stock out on other warehouses too
	# the code below checks the final entry of the item in other warehouses before the stock out date including the stock out date
	# if the final entry has a positive quantity, then the item was not stock out
	# if the final entry has a zero quantity, then the item was stock out

	data = frappe.db.sql("""
			SELECT t.* 
				FROM (
					SELECT 
						warehouse,
						qty_after_transaction,
						ROW_NUMBER() OVER (PARTITION BY warehouse ORDER BY posting_date, creation DESC) AS row_num
					FROM `tabStock Ledger Entry`
					WHERE 
						item_code = %s AND 
						posting_date <= %s and 
						warehouse not in ('US02-Houston - Active Stock - ICL', %s)
				) AS t
				WHERE t.row_num = 1;
		""", (item_code, date, warehouse), as_dict=1)

	for d in data:
		if d.get("qty_after_transaction") > 0:
			return False

	return True

def get_total_lifetime_sold(sales_data):
	total = 0
	for d in sales_data:
		total += d.get("qty")
	return total

def get_reference_warehouse(filters):
	warehouse = filters.get('reference_warehouse')
	warehouse_map = {
		"Total QOH": "total_actual_qty",
		"W01-WHS-Active Stock - ICL": "wh_whs",
		"R05-DTN-Active Stock - ICL": "wh_dtn",
		"R07-Queen-Active Stock - ICL": "wh_queen",
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
				"label": "ItemGroups",
				"fieldname": "itemgroups",
				"fieldtype": "Data",
				"width": 200
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
			"label": _(f"TotalSold12M"),
			"fieldname": "last_twelve_months",
			"fieldtype": "Int",
			"width": 140,
		},
		{
			"label": _(f"TotalSold24M"),
			"fieldname": "last_24_months",
			"fieldtype": "Int",
			"width": 140,
		},
		{
			"label": _("TotalSold"),
			"fieldname": "total_lifetime_sold",
			"fieldtype": "Int",
			"width": 140,
		},
		{
			"label": _(f"OnlineSold{filters.sales_data_period}M"),
			"fieldname": "sold_online",
			"fieldtype": "Int",
			"width": 140,
		},
		{
			"label": _(f"StoreSold{filters.sales_data_period}M"),
			"fieldname": "sold_in_store",
			"fieldtype": "Int",
			"width": 140,
		},
		{
			"label": _(f"GPDSalesQty{filters.sales_data_period}M"),
			"fieldname": "gpd_sales_qty",
			"fieldtype": "Float",
			"width": 140,
			"precision": 2
		},
		{
			"label": _(f"GPDSalesRev{filters.sales_data_period}M"),
			"fieldname": "gpd_sales_amount",
			"fieldtype": "Currency",
			"width": 140
		}
	])

	years_to_subtract = 1
	if filters.get("sales_data_period") == '12':
		years_to_subtract = 1
	elif filters.get("sales_data_period") == '24':
		years_to_subtract = 2

	today = getdate(nowdate())
	last_month = getdate(str(datetime(today.year-years_to_subtract, today.month,1)))
	
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
			"label": _(f"SaleRev{filters.sales_data_period}LM"),
			"fieldname": "sales_revenue_last_twelve_months",
			"fieldtype": "Currency",
			"width": 140
		},
		{
			"label": _(f"NoCustL12M"),
			"fieldname": "no_cust_l12m",
			"fieldtype": "Int",
			"width": 140,
		}, 
		{
			"label": _(f"NoCustL24M"),
			"fieldname": "no_cust_l24m",
			"fieldtype": "Int",
			"width": 140,
		}, 
		{
			"label": _("BegInvt"),
			"fieldname": "beginning_inventory",
			"fieldtype": "Float",
			"width": 140,
			"precision": 2
		},
		{
			"label": _("EndInvt"),
			"fieldname": "ending_inventory",
			"fieldtype": "Float",
			"width": 140,
			"precision": 2
		},
		{
			"label": _("InvtTOV"),
			"fieldname": "inventory_turnover",
			"fieldtype": "Float",
			"width": 140,
			"precision": 1
		},
		{
			"label": _("LT"),
			"fieldname": "lead_time_in_days",
			"fieldtype": "Int",
			"width": 140
		}
	])

	columns.extend([
		{
			"label": _(f"AvgOrderFreq12M"),
			"fieldname": "average_order_frequency_12",
			"fieldtype": "Int",
			"width": 140,
			"precision": 2
		},
		{
			"label": _(f"AvgOrderFreq24M"),
			"fieldname": "average_order_frequency_24",
			"fieldtype": "Int",
			"width": 140,
			"precision": 2
		},
		{
			"label": _(f"AvrgOrderQty{filters.sales_data_period}M"),
			"fieldname": "average_order_qty_last_twelve_months",
			"fieldtype": "Int",
			"precision": 2,
			"width": 140
		},
		{
			"label": _(f"DiscountPer{filters.sales_data_period}M"),
			"fieldname": "average_discount_last_twelve_months",
			"fieldtype": "Float",
			"precision": 2,
			"width": 140
		},
		{
			"label": "PUOM",
			"fieldname": "purchase_uom",
			"fieldtype": "Data",
			"width": 100
		},
		{
			"label": "MOO",
			"fieldname": "minimum_order_qty",
			"fieldtype": "Int",
			"width": 100
		},
		{
			"label": "SS",
			"fieldname": "safety_stock",
			"fieldtype": "Float",
			"width": 100,
			"precision": 2

		},
		{
			"label": "MthStck12M",
			"fieldname": "monthly_stock_12m",
			"fieldtype": "Float",
			"width": 100,
			"precision": 2
		},
		{
			"label": "MthStck24M",
			"fieldname": "monthly_stock_24m",
			"fieldtype": "Float",
			"width": 100,
			"precision": 2
		},
		{
			"label": f"NoStockOut{filters.sales_data_period}M",
			"fieldname": "no_stock_out_12m",
			"fieldtype": "Int"
		},
		{
			"label": _("ERPNextTemplate"),
			"fieldname": "erpnext_template",
			"fieldtype": "Data",
			"width": 200
		},
		{
			"label": "POReorderQty",
			"fieldname": "ais_poreorderqty",
			"fieldtype": "Float",
			"width": 100,
			"precision": 2
		},
		{
			"label": "POReorderLevel",
			"fieldname": "ais_poreorderlevel",
			"fieldtype": "Float",
			"width": 100,
			"precision": 2
		},
		{
			"label": "SuggQTO",
			"fieldname": "suggested_qty_to_order",
			"fieldtype": "Float",
			"width": 100,
			"precision": 2
		},
	])

	return columns

def get_master(conditions="", filters={}):
	data = frappe.db.sql("""
			select  
				i.ifw_retailskusuffix, i.item_code, i.item_name, i.image,
				i.asi_item_class, s.supplier, s.supplier_part_no, i.disabled, 
				country_of_origin,customs_tariff_number, ifw_duty_rate,
				ifw_discontinued,ifw_product_name_ci,ifw_item_notes,ifw_item_notes2,
				ifw_po_notes, ais_poreorderqty, ais_poreorderlevel, 
				s.ifw_supplier_qoh, i.stock_uom, i.purchase_uom, i.lead_time_days,
				i.min_order_qty, i.safety_stock, i.variant_of, i.ais_poreorderqty,
				i.ais_poreorderlevel, i.creation, i.item_group
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
		# format_strings = ','.join(['%s'] * len(suppliers))
		conditions += " and s.supplier IN %(supplier)s"
	if limit != "All":
		conditions += " limit {}".format(str(limit))
	return conditions

def get_monthly_consumption(item_code, created_at,filters, sales_data):
	average_monthly_consumption_12 = 0
	average_monthly_consumption_24 = 0
	today = getdate(nowdate())

	# get months passed since the item was created
	months_passed = (today.year - created_at.year) * 12 + today.month - getdate(created_at).month

	for i in range(1, 3):
		total_months = i * 12
		last_date = getdate(str(datetime(today.year-i, today.month, today.day)))
		monthly_consumption = {}

		for sd in sales_data:
			if sd.posting_date < last_date:
				continue

			# get month and year from sd posting_date
			month = getdate(sd.posting_date).month
			year = getdate(sd.posting_date).year

			key = f"{month}{year}"
			if key in monthly_consumption:
				monthly_consumption[key] += sd.qty
			else:
				monthly_consumption[key] = sd.qty

		# convert monthly_consumption to list
		monthly_consumption = list(monthly_consumption.values())

		if len(monthly_consumption) == 0:
			average_monthly_consumption = 0
		else:
			average_monthly_consumption = sum(monthly_consumption) / (months_passed if months_passed < total_months else total_months)

		average_monthly_consumption = (average_monthly_consumption * 100) / 100
		if i == 1:
			average_monthly_consumption_12 = average_monthly_consumption
		elif i == 2:
			average_monthly_consumption_24 = average_monthly_consumption

	return average_monthly_consumption_12, average_monthly_consumption_24

def get_inventory(item_code, warehouse):
	today = getdate(nowdate())
	start_date = str(today.year)+"-01-01"
	last_date = today

	return get_begining_ending_inventory(item_code, warehouse, start_date, last_date)

def get_begining_ending_inventory(item_code, warehouse, start_date, last_date):
	beginning_inventory = 0
	ending_inventory = 0
	
	# get stock balance report from the january 1st of the current year to the current date 
	filters = {
		"company": "International Camouflage Ltd",
		"item_code": item_code,
		"from_date": start_date,
		"to_date": last_date,
	}

	if warehouse:
		filters["warehouse"] = warehouse

	report = frappe.get_doc("Report", "Stock Balance")
	report.custom_columns = []

	report_result = generate_report_result(report, filters)
	result = report_result.get("result")

	if result:
		for r in result:
			if type(r) == list:
				continue

			beginning_inventory += r.get("opening_val")
			ending_inventory += r.get("bal_val")

	return (beginning_inventory * 100)/ 100,  (ending_inventory * 100) / 100
	
def get_gpd_sales(item_code, years_before):
	data = frappe.db.sql("""select sum(net_amount), sum(qty)
							from
								`tabSales Invoice Item` sii
							join `tabSales Invoice` si on si.name = sii.parent
							join `tabSales Order` so on so.name = sii.sales_order
							where
								so.source = "Website - GPD" and 
								sii.item_code = %s and
								si.docstatus = 1 and
								si.posting_date >= %s and
								(sii.warehouse <> 'US02-Houston - Active Stock - ICL')
		""",(item_code, years_before.strftime("%Y-%m-%d")))
	if data:
		return data[0]
	return 0

def get_discount_percentages(item_code, years_before):
	data = data = frappe.db.sql("""select discount_percentage
							from
								`tabSales Invoice Item` sii
							join
								`tabSales Invoice` si on si.name = sii.parent
							where
								sii.item_code = %s and 
								si.docstatus = 1 and 
								si.posting_date >= %s and 
								(sii.warehouse <> 'US02-Houston - Active Stock - ICL')
		""",(item_code, years_before.strftime("%Y-%m-%d")))

	discount_percentages = []
	for d in data:
		if d[0]:
			discount_percentages.append(d[0])

	return discount_percentages

def get_order_frequency(item_code, today):	
	year_before = getdate(str(datetime(today.year-1, today.month, today.day)))
	two_years_before = getdate(str(datetime(today.year-2, today.month, today.day)))
	six_months_before = today - relativedelta(months=6)

	order_freq_in_12_months = 0
	order_freq_in_24_months = 0

	# get total number of received purchase receipts
	data = frappe.db.sql("""select Month(posting_date) as month, pr.name, Year(posting_date) as year, pri.qty, pr.posting_date
							from
								`tabPurchase Receipt Item` pri
							join
								`tabPurchase Receipt` pr on pr.name = pri.parent
							where
								pri.item_code = %s and 
								pr.docstatus = 1 and 
								pr.posting_date >= %s and 
								pr.status = "Completed" and
								pri.warehouse not in ('US02-Houston - Active Stock - ICL', 'R04-Mon-Active Stock - ICL', 'R06-Reg-Active Stock - ICL')
		""",(item_code, two_years_before.strftime("%Y-%m-%d")), as_dict=1)

	order_frequency = {}
	ordered_qty = {}
	
	# group data by month
	for d in data:
		if d.posting_date >= year_before:
			order_freq_in_12_months += 1

		order_freq_in_24_months += 1

		if d.month in ordered_qty:
			ordered_qty[d.month] += d.qty
		else:
			ordered_qty[d.month] = d.qty

	# calculate average order frequency per month for the last 12 months and 24 months
	order_frequency["12"] = order_freq_in_12_months / 12 
	order_frequency["24"] = order_freq_in_24_months / 2  # This shows the average order frequency per year
	
	# convert ordered_qty to list
	ordered_qty = list(ordered_qty.values())

	return order_frequency, ordered_qty

def get_unique_customers_bought_an_item(item_code, today):
	year_before = getdate(str(datetime(today.year-1, today.month, today.day)))
	two_years_before = getdate(str(datetime(today.year-2, today.month, today.day)))

	data = frappe.db.sql("""
		select customer, `tabSales Invoice`.posting_date
		from 
			`tabSales Invoice Item` 
		join 
			`tabSales Invoice` on `tabSales Invoice`.name = `tabSales Invoice Item`.parent
		where 
			item_code = %s and 
			`tabSales Invoice`.docstatus = 1 and 
			`tabSales Invoice`.status = "Paid" and
			posting_date >= %s
			and `tabSales Invoice Item`.warehouse <> 'US02-Houston - Active Stock - ICL'
			""",
	(item_code, two_years_before.strftime("%Y-%m-%d")))

	# each pos customers are counted as one and other customers are counted using set

	number_of_pos_customer_12 = 0
	unique_customers_12 = set()

	number_of_pos_customer_24 = 0
	unique_customers_24 = set()

	for d in data:
		if d[1] >= year_before:
			if d[0].startswith("DefaultPOS"):
				number_of_pos_customer_12 += 1
			else:
				unique_customers_12.add(d[0])

		if d[0].startswith("DefaultPOS"):
			number_of_pos_customer_24 += 1
		else:
			unique_customers_24.add(d[0])		

	total_unique_customers_12 = len(unique_customers_12) + number_of_pos_customer_12
	total_unique_customers_24 = len(unique_customers_24) + number_of_pos_customer_24

	if data:
		return total_unique_customers_12, total_unique_customers_24
	return 0, 0

def get_sold_amount_in_dollars(item_code, years_before):
	amount = 0
	data = frappe.db.sql(""" 
		select sum(net_amount) from `tabSales Invoice Item`
			join `tabSales Invoice` on `tabSales Invoice`.name = `tabSales Invoice Item`.parent
		where 
			item_code = %s and 
			`tabSales Invoice`.status in ('Paid', 'Return') and
			posting_date >= %s and 
			`tabSales Invoice Item`.warehouse <> 'US02-Houston - Active Stock - ICL'
	""",(item_code, years_before.strftime("%Y-%m-%d")))

	if data:
		amount = data[0][0]
	return amount

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
	data= frappe.db.sql(f"""select 
							p.posting_date, c.qty, p.source, c.net_amount
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


def get_item_group_parents(lower_item_group):
	item_groups = []
	item_group = lower_item_group

	while item_group:
		item_group = frappe.db.get_value("Item Group", item_group, "parent_item_group")
		if item_group and item_group != "All Item Groups":
			item_groups.append(item_group)

	item_groups.insert(0, lower_item_group)
	item_groups.reverse()

	if len(item_groups) > 1:
		item_groups = ">".join(item_groups)
	else:
		item_groups = item_groups[0]

	return item_groups 