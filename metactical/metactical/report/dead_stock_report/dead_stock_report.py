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
	data = []
	columns = get_columns()
	warehouses = get_warehouses()
	masters = get_masters(warehouses)
	combo_dict = {}
	total = 0
	for i in masters:
		row = {}
		row["ifw_retailskusuffix"] = i.get("ifw_retailskusuffix")
		row["item_name"] = i.get("item_name")
		row["item_code"] = i.get("item_code")
		row["variant_of"] = i.get("variant_of")
		

		row["ifw_discontinued"] = int(i.get("ifw_discontinued"))
		row["supplier_sku"] = i.get("supplier_part_no")		
		row["supplier_name"] = i.get("supplier")
		row["date_created"] = (i.get("creation")).strftime("%d-%b-%y")

		row["asi_item_class"] = i.get("asi_item_class")

		row["rate"] = get_item_details(i.get("item_code"), "Selling")
		row["rate_camo"] = get_item_details(i.get("item_code"), "RET - Camo", "Selling" )
		row["rate_gpd"] = get_item_details(i.get("item_code"), "RET - GPD", "Selling", )


		row["date_last_received"] = get_date_last_received(i.get("item_code"), i.get("supplier"))
		#row["item_cost"] = get_item_details(i.get("item_code"), "Buying", i.get("suppliIDer"))
		row["item_cost"] = get_cost_details(i.get("item_code"), "Buying", i.get("suppliIDer"))

		row["wh_whs"] = get_qty(i.get("item_code"), "W01-WHS-Active Stock - ICL") or 0
		row["wh_dtn"] = get_qty(i.get("item_code"), "R05-DTN-Active Stock - ICL") or 0
		row["wh_queen"] = get_qty(i.get("item_code"), "R07-Queen-Active Stock - ICL") or 0
		row["wh_amb"] = get_qty(i.get("item_code"), "R06-AMB-Active Stock - ICL") or 0
		row["wh_mon"] = get_qty(i.get("item_code"), "R04-Mon-Active Stock - ICL") or 0
		row["wh_vic"] = get_qty(i.get("item_code"), "R03-Vic-Active Stock - ICL") or 0
		row["wh_edm"] = get_qty(i.get("item_code"), "R02-Edm-Active Stock - ICL") or 0
		row["wh_gor"] = get_qty(i.get("item_code"), "R01-Gor-Active Stock - ICL") or 0

		row["total_actual_qty"] = 0
		
		if row.get("wh_whs") > 0: 
			row["total_actual_qty"] += row.get("wh_whs")
		if row.get("wh_dtn") > 0:
			row["total_actual_qty"] += row.get("wh_dtn")
		if row.get("wh_queen") > 0:
			row["total_actual_qty"] += row.get("wh_queen")
		if row.get("wh_amb") > 0:
			row["total_actual_qty"] += row.get("wh_amb")
		if row.get("wh_mon") > 0:
			row["total_actual_qty"] += row.get("wh_mon")
		if row.get("wh_vic") > 0:
			row["total_actual_qty"] += row.get("wh_vic")
		if row.get("wh_edm") > 0:
			row["total_actual_qty"] += row.get("wh_edm")
		if row.get("wh_gor") > 0:
			row["total_actual_qty"] += row.get("wh_gor")
		
		row["tag"] = get_tags(i.get("item_code"))
		expected_pos = get_purchase_orders(i.get("item_code"), i.get("supplier"))
		row["expected_pos"] = expected_pos
		ordered_qty = get_open_po_qty(i.get("item_code"), i.get("supplier"))
		row["ordered_qty"] = ordered_qty or 0.0
		
		row["last_sold_date"] = get_date_last_sold(i.get("item_code"))
		sales_data = get_total_sold(i.get("item_code"))
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
			

			last12_month_date = today - relativedelta(years=1)
			if posting_date >= last12_month_date:
				row["last_twelve_months"] += qty

		total_active = row["wh_whs"] + row["wh_dtn"] + row["wh_queen"] + row["wh_edm"] + row["wh_gor"] + row["wh_vic"]
		if total_active > 0:
			data.append(row)

		#data.append(row)

	return columns, data

def get_columns():
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
				"label": "TemplateSKU (Variant of)",
				"options": "Item",
				"fieldname": "variant_of",
				"fieldtype": "Link",
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
				"label": _("Tags"),
				"fieldname": "tag",
				"fieldtype": "Data",
				"width": 100,
			},
			{
				"label": _("ItemClass"),
				"fieldname": "asi_item_class",
				"fieldtype": "Data",
				"width": 150,
				"align": "left",
			},
			
			{
				"label": _("Rate Camo"),
				"fieldname": "rate_camo",
				"fieldtype": "Currency",
				"width": 100,
			},
			{
				"label": _("Rate Gpd"),
				"fieldname": "rate_gpd",
				"fieldtype": "Currency",
				"width": 100,
			},
			{
				"label": _("SUP Cost"),
				"fieldname": "item_cost",
				"fieldtype": "Currency",
				"width": 100,
			},
			{
				"label": "Discontinued",
				"fieldname": "ifw_discontinued",
				"fieldtype": "Int",
				"width": 100,
				"align": "left",
			},
			{
				"label": _("OnOrderWarehouseActive"),
				"fieldname": "ordered_qty",
				"fieldtype": "Float",
				"width": 120,
			},
			{
				"label": _("DateLastReceived"),
				"fieldname": "date_last_received",
				"fieldtype": "DateTime",
				"width": 200,
				"align": "center",
			},
			{
				"label": _("Date Created"),
				"fieldname": "date_created",
				"fieldtype": "DateTime",
				"width": 200,
				"align": "center",
			},
			{
				"label": _("Default Supplier"),
				"fieldname": "supplier_name",
				"fieldtype": "Link",
				"options": "Supplier",
				"width": 200,
			},
			{
				"label": _("Suplier SKU"),
				"fieldname": "supplier_sku",
				"fieldtype": "Data",
				"width": 100,
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
				"label": _("R01-Gor-Active Stock - ICL"),
				"fieldname": "wh_gor",
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
				"label": _("R07-Queen-Active Stock - ICL"),
				"fieldname": "wh_queen",
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
				"label": _("TotalQOH"),
				"fieldname": "total_actual_qty",
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
	last_month = getdate(str(datetime(today.year, 1,1)))
	while last_month <= today:
		month = last_month.strftime("%B")
		columns.append({
        		"label": _(str(last_month.year) + "_Sold" + month),
                "fieldname": frappe.scrub("sold"+month+str(last_month.year)),
                "fieldtype": "Int",
                "width": 140,
		})
		last_month = last_month + relativedelta(months=1)

	end_loop_month = getdate(str(datetime(today.year, 1,1)))
	counter_month = getdate(str(datetime(today.year-1, 1,1)))
	while counter_month < end_loop_month:
		month = counter_month.strftime("%B")
		columns.append({
        		"label": _(str(counter_month.year) + "_Sold" + month),
                "fieldname": frappe.scrub("sold"+month+str(counter_month.year)),
                "fieldtype": "Int",
                "width": 140,
		})
		counter_month = counter_month + relativedelta(months=1)

	columns.extend([
        {
            "label": _("DateLastSold"),
            "fieldname": "last_sold_date",
            "fieldtype": "Data",
            "width": 100,
	}])
	return columns


def get_warehouses():
	ret = []
	warehouses = frappe.get_all('Warehouse', filters={"is_group": 0})
	for warehouse in warehouses:
		if "Active Stock" in warehouse.name:
			ret.append(warehouse.name)
	return ret
	

def get_masters(warehouses):
	data = frappe.db.sql("""SELECT 
								b.item_code, i.ifw_retailskusuffix, i.item_name,
								i.asi_item_class, i.variant_of, i.ifw_discontinued, i.creation,
								i.disabled, country_of_origin,customs_tariff_number, ifw_po_notes,
								ifw_duty_rate,ifw_discontinued,ifw_product_name_ci,ifw_item_notes,ifw_item_notes2,
								s.supplier, s.supplier_part_no
							FROM
								`tabBin` b
							LEFT JOIN `tabItem` i ON b.item_code = i.name
							LEFT JOIN `tabItem Supplier` s ON s.parent = i.name
							WHERE
								b.actual_qty > 0 AND b.warehouse in %(warehouses)s
							GROUP BY item_code""", {"warehouses": warehouses} , as_dict=1)
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
	data= frappe.db.sql("""select max(transaction_date) from `tabPurchase Order` p inner join 
		`tabPurchase Order Item` c on p.name = c.parent where c.item_code = %s and p.supplier=%s and p.docstatus = 1
		""",(item,supplier))
	if data:
		date = data[0][0]
	if date:
		date = getdate(date)
		date = date.strftime("%d-%b-%y")
	return date

def get_date_last_sold(item):
	date = None
	data= frappe.db.sql("""select max(posting_date) from `tabSales Invoice` p inner join 
		`tabSales Invoice Item` c on p.name = c.parent where c.item_code = %s and p.docstatus = 1
		""",(item))
	if data:
		date = data[0][0]
	if date:
		date = getdate(date)
		date = date.strftime("%d-%b-%y")
	return date

def get_total_sold(item):
	data= frappe.db.sql("""select p.posting_date, c.qty from `tabSales Invoice` p inner join 
		`tabSales Invoice Item` c on p.name = c.parent where c.item_code = %s and p.docstatus = 1
		""",(item), as_dict=1)
	return data

def get_qty(item, warehouse):
	qty = 0
	data= frappe.db.sql("""select actual_qty-reserved_qty from `tabBin`
		where item_code = %s and warehouse=%s
		""",(item,warehouse))
	if data:
		qty = data[0][0] or 0
	return qty

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
		 """,(item))
	if data:
		return data[0][0]
	return 0

@frappe.whitelist()
def get_item_details(item, price_list, list_type="Selling",  supplier=None):
	cond = " and selling = 1"
	
	if list_type == "Buying": cond= " and buying = 1"
	rate = 0
	date = frappe.utils.nowdate()
	r = frappe.db.sql("""select price_list_rate from `tabItem Price` where '{}' between valid_from and valid_upto and item_code = '{}'
	and price_list = '{}' {} limit 1""".format(date, item,price_list, cond))
	if r:
		if r[0][0]:
			rate = r[0][0]
	else:
		r = frappe.db.sql("""select price_list_rate from `tabItem Price`
			where (valid_from <= '{}' or valid_upto >= '{}')
			and item_code = '{}' and price_list = '{}'
			{} limit 1""".format(date, date, item, price_list, cond))
		if r:
			if r[0][0]:
				rate = r[0][0]
		else:
			r = frappe.db.sql("""select price_list_rate from `tabItem Price` 
				where valid_from IS NULL and valid_upto IS NULL and item_code = '{}' 
				and price_list = '{}' {} limit 1""".format(item, price_list, cond))
			if r:
				if r[0][0]:
					rate = r[0][0]
	return rate

@frappe.whitelist()
def get_cost_details(item, list_type="Buying",  supplier=None):
	
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
