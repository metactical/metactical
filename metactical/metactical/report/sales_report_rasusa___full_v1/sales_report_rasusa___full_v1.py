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

def execute(filters=None):
	if not filters:
		filters = {}

	#frappe.throw(filters.get("limit"))
	conditions = get_conditions(filters)
	#frappe.throw(conditions)
	columns = get_column(filters,conditions)
	data = []
	
	# #frappe.msgprint(filters)
	# #frappe.msgprint('filters: {0}'.format(filters))
	master = get_master(conditions,filters)
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
		row["country_of_origin"] = i.get("country_of_origin")
		row["customs_tariff_number"] = i.get("customs_tariff_number")

		row["supplier_sku"] = i.get("supplier_part_no")
		
		row["supplier_name"] = i.get("supplier")
		
		row["barcode"] = frappe.db.get_value("Item Barcode", {"parent": i.get("item_code")}, "barcode")

		row["item_image"] =  "<a target="+str("_blank")+" href = "+str(i.get("image"))+"> "+str(i.get("image"))+" </a>"   

		row["rate"] = get_item_details(i.get("item_code"), "Selling")
		# row["item_discontinued"] = i.get("disabled")
		row["date_last_received"] = get_date_last_received(i.get("item_code"), i.get("supplier"))
		row["item_cost"] = get_item_details(i.get("item_code"), "Buying", i.get("supplier"))
		
		row["wh_whs"] = get_qty(i.get("item_code"), "W01-WHS-Active Stock - ICL") or 0
		row["wh_dtn"] = get_qty(i.get("item_code"), "R05-DTN-Active Stock - ICL") or 0
		row["wh_queen"] = get_qty(i.get("item_code"), "R07-Queen-Active Stock - ICL") or 0
		row["wh_amb"] = get_qty(i.get("item_code"), "R06-AMB-Active Stock - ICL") or 0
		row["wh_mon"] = get_qty(i.get("item_code"), "R04-Mon-Active Stock - ICL") or 0
		row["wh_vic"] = get_qty(i.get("item_code"), "R03-Vic-Active Stock - ICL") or 0
		row["wh_edm"] = get_qty(i.get("item_code"), "R02-Edm-Active Stock - ICL") or 0
		row["wh_gor"] = get_qty(i.get("item_code"), "R01-Gor-Active Stock - ICL") or 0
		row["wh_ushp"] = get_qty(i.get("item_code"), "US01-ShipCalm-Active Stock - ICL") or 0

		row["total_actual_qty"] = (row.get("wh_whs") or 0)+(row.get("wh_dtn") or 0)+(row.get("wh_queen") or 0)+(row.get("wh_amb") or 0)+(row.get("wh_mon") or 0)+(row.get("wh_vic") or 0)+(row.get("wh_edm") or 0)+(row.get("wh_gor") or 0)
		row["material_request"] = get_open_material_request(i.get("item_code"))
		row["tag"] = get_tags(i.get("item_code"))
		expected_pos = get_purchase_orders(i.get("item_code"), i.get("supplier"))
		row["expected_pos"] = expected_pos
		row["po_eta"] = get_last_purchase_orders(i.get("item_code"), i.get("supplier"))
		ordered_qty = get_open_po_qty(i.get("item_code"), i.get("supplier"))
		row["ordered_qty"] = ordered_qty or 0.0
		row["last_sold_date"] = get_date_last_sold(i.get("item_code"), "Website - RASUSA")
		sales_data = get_total_sold(i.get("item_code"), "Website - RASUSA")
		row["previous_year_sale"] = 0
		row["total"] = 0
		row["last_twelve_months"] = 0

		today = getdate(nowdate())
		last_year = today.year-1
		current_year = today.year

		last_month = getdate(str(datetime(today.year-1, 1,1)))
		while last_month <= today:
			month = last_month.strftime("%B")
			row[frappe.scrub("sold"+month+str(last_month.year))]=0
			last_month = last_month + relativedelta(months=1)

		row["sold_last_ten_days"] = 0
		row["sold_last_thirty_days"] = 0
		row["sold_last_sixty_days"] = 0
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

			sold_last_ten_days = today - timedelta(days=10)
			sold_last_thirty_days = today - timedelta(days=30)
			sold_last_sixty_days = today - timedelta(days=60)

			if posting_date >= sold_last_sixty_days:
				row["sold_last_sixty_days"] += qty
				if posting_date >= sold_last_thirty_days:
					row["sold_last_thirty_days"] += qty
					if posting_date >= sold_last_ten_days:
						row["sold_last_ten_days"] += qty
		data.append(row)

	return columns, data

def get_column(filters,conditions):
	columns = [
			{
				"label": _("RetailSkuSuffix"),
				"fieldname": "ifw_retailskusuffix",
				"fieldtype": "Data",
				"width": 150,
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
				"fieldtype": "Float",
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
			# {
			# 	"label": _("Discointinued"),
			# 	"fieldname": "item_discontinued",
			# 	"fieldtype": "Boolean",
			# 	"width": 100,
			# 	"default": False,
			# },
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
				"label": _("R06-AMB-Active Stock - ICL"),
				"fieldname": "wh_amb",
				"fieldtype": "Int",
				"width": 200,
			},
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
			},
			{
				"label": _("US01-ShipCalm-Active Stock"),
				"fieldname": "wh_ushp",
				"fieldtype": "Int",
				"width": 200,
			},
			{
				"label": _("TotalQOH"),
				"fieldname": "total_actual_qty",
				"fieldtype": "Int",
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
				"label": _("OrderedQty"),
				"fieldname": "ordered_qty",
				"fieldtype": "Float",
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
			}]
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
	}])
	return columns


def get_master(conditions="", filters={}):
	data = frappe.db.sql("""select  i.ifw_retailskusuffix, i.item_code, i.item_name, i.image,
			s.supplier, s.supplier_part_no, i.disabled, i.country_of_origin,i.customs_tariff_number,
			i.ifw_duty_rate,i.ifw_discontinued,i.ifw_product_name_ci,i.ifw_item_notes,i.ifw_item_notes2,
			i.ifw_po_notes
			from `tabItem Supplier` s inner join `tabItem` i on i.name = s.parent
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
	
	if limit and limit != "All":
		conditions += " limit {}".format(str(limit))
	return conditions

def get_date_last_received(item, supplier):
	date = None
	data= frappe.db.sql("""select max(transaction_date) from `tabPurchase Order` p inner join 
		`tabPurchase Order Item` c on p.name = c.parent where c.item_code = %s and p.supplier=%s and p.docstatus = 1
		""",(item,supplier))
	if data:
		date = data[0][0]
	if date:
		date = getdate(date)
		date = date.strftime("%d-%b-%Y")
	return date

def get_date_last_sold(item, lead_source):
	date = None
	data= frappe.db.sql("""select max(posting_date) from `tabSales Invoice` p inner join 
		`tabSales Invoice Item` c on p.name = c.parent where c.item_code = %s and p.docstatus = 1
		and p.source = %s
		""",(item, lead_source))
	if data:
		date = data[0][0]
	if date:
		date = getdate(date)
		date = date.strftime("%d-%b-%Y")
	return date

def get_total_sold(item, lead_source):
	data= frappe.db.sql("""select p.posting_date, c.qty from `tabSales Invoice` p inner join 
		`tabSales Invoice Item` c on p.name = c.parent where c.item_code = %s and p.docstatus = 1
		and p.source = %s
		""",(item, lead_source), as_dict=1)
	return data

def get_qty(item, warehouse):
	qty = 0
	data= frappe.db.sql("""select actual_qty-reserved_qty from `tabBin`
		where item_code = %s and warehouse=%s
		""",(item,warehouse))
	if data:
		qty = data[0][0] or 0
	return qty

def get_open_material_request(item):
	material_requests = ""
	data = frappe.db.sql("""select p.name, c.qty from `tabMaterial Request` p inner join 
		`tabMaterial Request Item` c on c.parent = p.name where p.docstatus=1 and c.item_code = %s""",(item))
	for d in data:
		material_requests += d[0]+" ("+str(d[1])+"), "
	return material_requests

def get_tags(item):
	output = ""
	data = frappe.db.sql("""select tag from `tabTag Link` where document_type='Item' and document_name = %s""",(item))
	for d in data:
		output += d[0]+", "
	return output

def get_purchase_orders(item,supplier):
	output = ""
	data = frappe.db.sql("""select p.name, c.qty-c.received_qty, c.schedule_date from `tabPurchase Order` p inner join 
		`tabPurchase Order Item` c on p.name = c.parent where p.docstatus=1 and c.item_code = %s
		and c.received_qty < c.qty and p.status in ("To Receive and Bill", "To Receive")
		 and p.supplier = %s""",(item, supplier))
	for d in data:
		# output += d[0]+" ("+str(d[1])+")("+str(getdate(d[2]).strftime("%d-%b-%Y"))+"),"
		output += d[0]+" ("+str(d[1])+"), "
	return output

def get_last_purchase_orders(item,supplier):
	output = ""
	data = frappe.db.sql("""select p.name, c.qty-c.received_qty, c.schedule_date from `tabPurchase Order` p inner join 
		`tabPurchase Order Item` c on p.name = c.parent where p.docstatus=1 and c.item_code = %s
		and c.received_qty < c.qty and p.status in ("To Receive and Bill", "To Receive")
		 and p.supplier = %s order by c.schedule_date desc limit 1""",(item, supplier))
	for d in data:
		output = d[0]+" ("+str(getdate(d[2]).strftime("%d-%b-%Y"))+")"
		# output = d[0]+" ("+str(d[1])+")"
	return output

def get_open_po_qty(item,supplier):
	output = ""
	data = frappe.db.sql("""select SUM(c.qty) - SUM(c.received_qty) from `tabPurchase Order` p inner join 
		`tabPurchase Order Item` c on p.name = c.parent where p.docstatus=1 and c.item_code = %s
		and c.received_qty < c.qty and  p.status in ("To Receive and Bill", "To Receive")
		 and p.supplier = %s""",(item, supplier))
	if data:
		return data[0][0]
	return 0

@frappe.whitelist()
def get_item_details(item, list_type="Selling", supplier=None):
	cond = " and selling = 1"
	if list_type == "Buying": cond= " and buying = 1"
	rate = 0
	date = frappe.utils.nowdate()
	r = frappe.db.sql("select price_list_rate from `tabItem Price` where '{}' between valid_from and valid_upto and item_code = '{}' {} limit 1".format(date, item, cond))
	if r:
		if r[0][0]:
			rate = r[0][0]
	else:
		r = frappe.db.sql("select price_list_rate from `tabItem Price` where (valid_from <= '{}' or valid_upto >= '{}') and item_code = '{}' {} limit 1".format(date, date, item, cond))
		if r:
			if r[0][0]:
				rate = r[0][0]
		else:
			r = frappe.db.sql("select price_list_rate from `tabItem Price` where valid_from IS NULL and valid_upto IS NULL and item_code = '{}' {} limit 1".format(item, cond))
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