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
	data = get_masters(warehouses)
	combo_dict = {}
	total = 0
	for row in data:
		row["date_created"] = (row.get("creation")).strftime("%d-%b-%y")

		row["rate_camo"] = get_item_details(row.get("item_code"), "RET - Camo", "Selling" )
		row["rate_gpd"] = get_item_details(row.get("item_code"), "RET - GPD", "Selling", )

		row["date_last_received"] = (
			getdate(row.get("latest_transaction_date")).strftime("%d-%b-%y")
			if row.get("latest_transaction_date") else ""
		)

		row["item_cost"] = get_cost_details(row.get("item_code"), "Buying", row.get("suppliIDer"))

		row["wh_whs"] = get_qty(row.get("item_code"), "W01-WHS-Active Stock - ICL") or 0
		row["wh_dtn"] = get_qty(row.get("item_code"), "R05-DTN-Active Stock - ICL") or 0
		row["wh_queen"] = get_qty(row.get("item_code"), "R07-Queen-Active Stock - ICL") or 0
		row["wh_amb"] = get_qty(row.get("item_code"), "R06-AMB-Active Stock - ICL") or 0
		row["wh_mon"] = get_qty(row.get("item_code"), "R04-Mon-Active Stock - ICL") or 0
		row["wh_vic"] = get_qty(row.get("item_code"), "R03-Vic-Active Stock - ICL") or 0
		row["wh_edm"] = get_qty(row.get("item_code"), "R02-Edm-Active Stock - ICL") or 0
		row["wh_gor"] = get_qty(row.get("item_code"), "R01-Gor-Active Stock - ICL") or 0

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
		
		row["tag"] = get_tags(row.get("item_code"))
		ordered_qty = get_open_po_qty(row.get("item_code"), row.get("supplier"))
		row["ordered_qty"] = ordered_qty or 0.0
		
		row["last_sold_date"] = get_date_last_sold(row.get("item_code"))
		sales_data = get_total_sold(row.get("item_code"))
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
			}
	]
	today = getdate(nowdate())
	last_month = getdate(str(datetime(today.year, 1,1)))
	while last_month <= today:
		month = last_month.strftime("%B")
		columns.append({
			"label": _(str(last_month.year) + "_Sold" + month),
			"fieldname": frappe.scrub("sold" + month + str(last_month.year)),
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
			"fieldname": frappe.scrub("sold" + month + str(counter_month.year)),
			"fieldtype": "Int",
			"width": 140,
		})
		counter_month = counter_month + relativedelta(months=1)

	columns.extend([{
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
	#warehouses_conditions = f"""AND b.warehouse IN ({','.join(['%s'] * len(warehouses))})""" if warehouses else ""
	warehouses_conditions = ""

	query = f"""
		SELECT 
			item.ifw_retailskusuffix, item.item_code, 
			item.variant_of, item.item_name,
			GROUP_CONCAT(tags.tag, ', ') as tag,
			item.asi_item_class,  
			camo_price.price_list_rate as rate_camo,
			gpd_price.price_list_rate as rate_gpd,
			item.last_purchase_rate AS item_cost,
			item.ifw_discontinued, 
			SUM(bin.ordered_qty) AS ordered_qty,
			MAX(sle.posting_date) AS date_last_received,
			item.creation AS date_created,
			defaults.default_supplier AS supplier_name,
			item_supplier.supplier_part_no AS supplier_sku,
			(wh_bin.actual_qty - wh_bin.reserved_qty) AS wh_whs,
			(dtn_bin.actual_qty - dtn_bin.reserved_qty) AS wh_dtn,
			(queen_bin.actual_qty - queen_bin.reserved_qty) AS wh_queen,
			(amb_bin.actual_qty - amb_bin.reserved_qty) AS wh_amb,
			(mon_bin.actual_qty - mon_bin.reserved_qty) AS wh_mon,
			(vic_bin.actual_qty - vic_bin.reserved_qty) AS wh_vic,
			(edm_bin.actual_qty - edm_bin.reserved_qty) AS wh_edm,
			(gor_bin.actual_qty - gor_bin.reserved_qty) AS wh_gor,
			(
				(wh_bin.actual_qty - wh_bin.reserved_qty) + 
				(dtn_bin.actual_qty - dtn_bin.reserved_qty) + 
				(queen_bin.actual_qty - queen_bin.reserved_qty) + 
				(amb_bin.actual_qty - amb_bin.reserved_qty) + 
				(mon_bin.actual_qty - mon_bin.reserved_qty) + 
				(vic_bin.actual_qty - vic_bin.reserved_qty) + 
				(edm_bin.actual_qty - edm_bin.reserved_qty) + 
				(gor_bin.actual_qty - gor_bin.reserved_qty)
			) AS total_actual_qty,
			item.disabled, item.country_of_origin, item.customs_tariff_number, item.ifw_po_notes,
			item.ifw_duty_rate, item.ifw_discontinued, item.ifw_product_name_ci, item.ifw_item_notes,
			item.ifw_item_notes2
		FROM
			`tabItem` item
		LEFT JOIN
			`tabTag Link` tags ON  tags.document_type = 'Item' AND tags.document_name = item.item_code
		LEFT JOIN
			`tabItem Price` camo_price ON 
				camo_price.item_code = item.item_code AND camo_price.price_list = 'RET - Camo' AND camo_price.selling = 1
		LEFT JOIN
			`tabItem Price` gpd_price ON 
				gpd_price.item_code = item.item_code AND gpd_price.price_list = 'RET - GPD' AND gpd_price.selling = 1
		LEFT JOIN
			`tabBin` bin ON bin.item_code = item.item_code
		LEFT JOIN
			`tabStock Ledger Entry` sle ON sle.item_code = item.item_code AND voucher_type = 'Purchase Receipt'
		LEFT JOIN
			(SELECT * FROM `tabItem Default` WHERE parent = item.item_code ORDER BY idx LIMIT 1) 
				AS defaults ON defaults.parent = item.item_code
		LEFT JOIN
			`tabBin` AS wh_bin ON wh_bin.item_code = item.item_code AND wh_bin.warehouse = 'W01-WHS-Active Stock - ICL'
		LEFT JOIN
			`tabBin` AS dtn_bin ON dtn_bin.item_code = item.item_code AND dtn_bin.warehouse = 'R05-DTN-Active Stock - ICL'
		LEFT JOIN
			`tabBin` AS queen_bin ON queen_bin.item_code = item.item_code AND queen_bin.warehouse = 'R07-Queen-Active Stock - ICL'
		LEFT JOIN
			`tabBin` AS amb_bin ON amb_bin.item_code = item.item_code AND amb_bin.warehouse = 'R06-AMB-Active Stock - ICL'
		LEFT JOIN
			`tabBin` AS mon_bin ON mon_bin.item_code = item.item_code AND mon_bin.warehouse = 'R04-Mon-Active Stock - ICL'
		LEFT JOIN
			`tabBin` AS vic_bin ON vic_bin.item_code = item.item_code AND vic_bin.warehouse = 'R03-Vic-Active Stock - ICL'
		LEFT JOIN
			`tabBin` AS edm_bin ON edm_bin.item_code = item.item_code AND edm_bin.warehouse = 'R02-Edm-Active Stock - ICL'
		LEFT JOIN
			`tabBin` AS gor_bin ON gor_bin.item_code = item.item_code AND gor_bin.warehouse = 'R01-Gor-Active Stock - ICL'
		LEFT JOIN
			`Item Supplier` AS item_supplier ON item_supplier.parent = item.item_code A
				ND item_supplier.supplier = defaults.default_supplier
		WHERE
			item.is_stock_item = 1
		GROUP BY 
			item_code
		LIMIT 10
	"""

	data = frappe.db.sql(query, as_dict=1)
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
	query = f"""
		select max(transaction_date)
		from `tabPurchase Order` purchase_order
		inner join
			`tabPurchase Order Item` purchase_order_item on purchase_order.name = purchase_order_item.parent
		where purchase_order_item.item_code = {item}
		and purchase_order.supplier = {supplier}
		and purchase_order.docstatus = 1
	"""
	data = frappe.db.sql(query)
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
