# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.desk.reportview import build_match_conditions
from frappe.utils import flt, cint, getdate, now, date_diff 

def execute(filters=None):
	if not filters:
		filters = {}

	columns = get_column()
	data=[]

	item_sales = get_data(filters)
 
	for d in item_sales:
		if d.item_code != "9999-tempt" and d.variant_of != "9999-tempt": #remove shipping items from list
			if d.get('price_list_rate') > 0 and d.get("item_name") != "Restock Fee":
				price_list_rate = frappe.db.get_value("Item Price", 
					{"price_list": d.get('selling_price_list'), "selling": 1, "item_code": d.get('item_code')}, "price_list_rate")
				if price_list_rate is not None:
					rate_discount = (price_list_rate - d.get('rate'))/d.get('price_list_rate')
					if rate_discount >= 0.15:
						row = {}
						comment, approver = get_comment_and_approver(d.item_code, d.name)

						row['si_date'] = d.posting_date
						row['warehouse'] = get_branch_name_mapping().get(d.warehouse, "")
						row['si_name'] = d.name
						row['ifw_retailskusuffix'] = d.ifw_retailskusuffix
						row['item_code'] = d.item_code
						row['item_name'] = d.item_name if len(d.item_name) < 100 else d.item_name[:100]
						row['qty'] = d.qty
						row['rate'] = d.rate
						row['price_list_rate'] = price_list_rate
						row['discount_percentage'] = rate_discount * 100
						row['uom'] = d.uom
						row['ifw_location'] = d.ifw_location
						row['cashier'] = frappe.db.get_value("User", d.owner, "first_name") or d.owner
						row['approver'] = approver
						row['comment'] = comment if len(comment) < 100 else comment[:100]

						data.append(row)

	return columns, data

def get_comment_and_approver(item_code, si_name):
	comment = ""
	approver = ""

	log_entries = frappe.db.get_list(
		"POS API Log",
		filters={"sales_invoice": si_name},
		fields=["payload"]
	)

	if log_entries:
		payload_raw = log_entries[0].payload
		if payload_raw:
			payload = frappe.parse_json(payload_raw)

			approvals = payload.get("ApprovalList", [])
			for approval in approvals:
				if approval.get("ItemId") == item_code:
					approver = approval.get("ManagerId")
					break

			comments = payload.get("Comments", [])
			for comment_item in comments:
				if comment_item.get("UserId") == approver:
					comment = comment_item.get("Text")
					break

	return comment, approver
 
def get_column():
	return [
		{
			"fieldname":"warehouse",
			"label": "Pos location",
			"fieldtype": "Data",
			'width': 200
		},
		{
			"fieldname": "si_name",
			"label": "Invoice Number",
			"fieldtype": 'Link',
			'options': 'Sales Invoice',
			'width': 120
		},
		{
			"fieldname":"ifw_retailskusuffix",
			"label": "Retail SkuSuffix",
			"fieldtype": "Data",
			'width': 200
		},
		{
			"fieldname":"item_name",
			"label": "Item Name",
			"fieldtype": "Data",
			'width': 200
		},
		{
			"fieldname":"price_list_rate",
			"label": "PriceList Price",
			"fieldtype": "Currency",
			"width": 120,
		},
		{
			"fieldname":"rate",
			"label": "Discount Price sold for",
			"fieldtype": "Currency",
			"width": 120,
		},
		{
			"fieldname":"discount_percentage",
			"label": "Percentage Amount(%)",
			"fieldtype": "Percent",
			'width': 120
		},
		{
			"fieldname":"cashier",
			"label": "Cashier",
			"fieldtype": "Text",
			'width': 150
		},
		{
			"fieldname": "approver",
			"label": "Approver",
			"fieldtype": "Text",
			'width': 150
		},
		{
			"fieldname": "comment",
			"label": "Comment",
			"fieldtype": "Text",
			'width': 200
		}
	]


def get_data(filters):
	where_filter = {"from_date": filters.from_date, "to_date": filters.to_date}
	where = ""

	data = frappe.db.sql("""select c.item_code, c.item_name, c.qty, c.price_list_rate, c.rate, c.discount_percentage,
		c.uom, c.ifw_retailskusuffix, c.ifw_location, c.warehouse,
		p.name, p.posting_date, p.selling_price_list, i.variant_of, p.owner
		from `tabSales Invoice Item` c inner join `tabSales Invoice` p on p.name = c.parent
		inner join `tabItem` i on c.item_code = i.name 
		where p.docstatus = 1 and p.posting_date BETWEEN %(from_date)s AND %(to_date)s
		order by c.warehouse, p.posting_date
		"""+ where, where_filter, as_dict=1)
	return data

def get_branch_name_mapping():
    return {
		"US01-Houston-Active - AOI": "Camo - Houston",
		"SS01-Hubert-Active - SS": "Camo - MTL",
		"RM02-Oshawa-Active - ZE": "Camo - Oshawa",
		"RM01-Bermondsey-Active - ZE": "Camo - Bermonsy",
		"R07-Queen-Active Stock - ICL": "Camo - Quen",
		"R05-DTN-Active Stock - ICL": "Camo - DT",
		"R03-Vic-Active Stock - ICL": "Camo - Vic",
		"R02-Edm-Active Stock - ICL": "Camo - Edm",
		"R01-Gor-Active Stock - ICL": "Gorilla - Van",
		"R08-Chilliwack-Active Stock - ICL": "Camo - Chi"
	}