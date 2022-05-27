# Copyright (c) 2022, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe

def execute(filters=None):
	columns, data = [], []
	init_data, suppliers = get_data()
	data = organise_data(init_data, suppliers)
	 
	columns=[
		{
			"fieldname": "supplier",
			"label": "Supplier",
			"fieldtype": "Link",
			"options": "Supplier",
			"width": 150
		},
		{
			"fieldname": "total_po_amount",
			"label": "Total PO Amount",
			"fieldtype": "Currency",
			"width": 150
		},
		{
			"fieldname": "total_bo_amount",
			"label": "Total BO Amount",
			"fieldtype": "Currency",
			"width": 150
		},
		{
			"fieldname": "create_po",
			"label": "",
			"fieldtype": "Data",
			"width": 150
		}
	]
	return columns, data

def organise_data(data, suppliers):
	rdata = []
	if len(data) == 0:
		return rdata
	for supplier in suppliers:
		row = {"supplier": supplier, "total_po_amount": 0, "total_bo_amount": 0}
		for r in data: 
			if r.get("supplier") == supplier and r.get("qty_to_order") > 0:
				row["total_po_amount"] += r.get("total_price", 0)
				row["total_bo_amount"] += r.get("bo_amount", 0)
		if row["total_po_amount"] > 0:
			row["create_po"] = '<button onClick="create_po(\'' + row['supplier'] + '\')">Create PO</button>'
			rdata.append(row)
	return rdata

def get_data(supplier=None):
	where = ''
	where_filter = {}
	suppliers = []
	if supplier is not None:
		where = "WHERE tis.supplier = %(supplier)s"
		where_filter = {"supplier": supplier}
	items = frappe.db.sql("""SELECT 
								tis.supplier, item.item_code, item.ais_poreorderqty, item.ais_poreorderlevel
							FROM
								`tabItem Supplier` AS tis
							LEFT JOIN
								`tabItem` AS item ON tis.parent = item.name
							""" + where, where_filter, as_dict=1)
	for item in items:
		if item.supplier not in suppliers:
			suppliers.append(item.supplier)
		item["wh_whs"] = get_qty(item.get("item_code"), "W01-WHS-Active Stock - ICL") or 0
		item["wh_dtn"] = get_qty(item.get("item_code"), "R05-DTN-Active Stock - ICL") or 0
		item["wh_queen"] = get_qty(item.get("item_code"), "R07-Queen-Active Stock - ICL") or 0
		item["wh_amb"] = get_qty(item.get("item_code"), "R06-AMB-Active Stock - ICL") or 0
		item["wh_mon"] = get_qty(item.get("item_code"), "R04-Mon-Active Stock - ICL") or 0
		item["wh_vic"] = get_qty(item.get("item_code"), "R03-Vic-Active Stock - ICL") or 0
		item["wh_edm"] = get_qty(item.get("item_code"), "R02-Edm-Active Stock - ICL") or 0
		item["wh_gor"] = get_qty(item.get("item_code"), "R01-Gor-Active Stock - ICL") or 0
		item["total_actual_qty"] = 0
		if item.get("wh_whs") > 0: 
			item["total_actual_qty"] += item.get("wh_whs")
		if item.get("wh_dtn") > 0:
			item["total_actual_qty"] += item.get("wh_dtn")
		if item.get("wh_queen") > 0:
			item["total_actual_qty"] += item.get("wh_queen")
		if item.get("wh_amb") > 0:
			item["total_actual_qty"] += item.get("wh_amb")
		if item.get("wh_mon") > 0:
			item["total_actual_qty"] += item.get("wh_mon")
		if item.get("wh_vic") > 0:
			item["total_actual_qty"] += item.get("wh_vic")
		if item.get("wh_edm") > 0:
			item["total_actual_qty"] += item.get("wh_edm")
		if item.get("wh_gor") > 0:
			item["total_actual_qty"] += item.get("wh_gor")
		#For Quantity to order
		item['material_requests'], item['mr_total_qty'] = get_open_material_request(item.get("item_code"))
		item["item_price"] = get_price(item.get("item_code"), item.get("supplier"))
		item['bo_amount'] = item.get("mr_total_qty", 0) * item.get("item_price", 0)
		item['ordered_qty'] = get_open_po_qty(item.get("item_code"), item.get("supplier")) or 0
		if item.get("total_actual_qty", 0) <= item.get("ais_poreorderlevel", 0):
			item["qty_to_order"] = item.get("ais_poreorderqty", 0)
		#Add material requests total and remove submitted purchase orders
		item["qty_to_order"] = item.get("qty_to_order", 0) + item.get("mr_total_qty", 0) - item.get("ordered_qty", 0)
		if item["qty_to_order"] < 0:
			item["qty_to_order"] = 0
		if item["qty_to_order"] > 0:
			item["total_price"] = item["item_price"] * item["qty_to_order"]
	return items, suppliers
			
def get_price(item, supplier):
	price_list = frappe.db.get_value('Supplier', supplier, 'default_price_list')
	price = frappe.db.get_value('Item Price', {"price_list": price_list, "buying": 1, "item_code": item}, 'price_list_rate')
	if price is not None and price != '':
		return price
	else:
		return 0

def get_open_po_qty(item,supplier):
	output = ""
	data = frappe.db.sql("""select SUM(c.qty) - SUM(c.received_qty) from `tabPurchase Order` p inner join 
		`tabPurchase Order Item` c on p.name = c.parent where p.docstatus=1 and c.item_code = %s
		and c.received_qty < c.qty and  p.status in ("To Receive and Bill", "To Receive")
		 and p.supplier = %s""",(item, supplier))
	if data:
		return data[0][0]
	return 0
	
def get_qty(item, warehouse):
	qty = 0
	data= frappe.db.sql("""select actual_qty-reserved_qty AS qty from `tabBin`
		where item_code = %s and warehouse=%s
		""",(item,warehouse), as_dict=1)
	if data and data[0]['qty'] > 0:
		qty = data[0]['qty']
	return qty
	
def get_open_material_request(item):
	total_qty = 0
	data = frappe.db.sql("""SELECT 
								mr.name as parent, mri.name as mritem, mri.qty
							FROM 
								`tabMaterial Request Item` AS mri
							LEFT JOIN
								`tabMaterial Request` AS mr ON mri.parent = mr.name
							WHERE 
								mr.docstatus=1 and mri.item_code = %(item)s 
								AND mr.status IN ('Pending', 'Partially Ordered')""", 
							{"item": item}, as_dict=1)
	if len(data) > 0:
		for row in data:
			total_qty += row.qty
	return data, total_qty
	
@frappe.whitelist()
def create_po(**args):
	args = frappe._dict(args)
	supplier = args.supplier
	if supplier is None or supplier=='':
		return
	price_list = frappe.db.get_value('Supplier', supplier, 'default_price_list')
	doc = frappe.new_doc("Purchase Order")
	doc.update({
		"supplier": supplier,
		"buying_price_list": price_list
	})
	items, suppliers = get_data(supplier)
	for item in items:
		if item.get("qty_to_order", 0) > 0:
			if item["mr_total_qty"] > 0:
				for mr in item["material_requests"]:
					doc.append("items", {
						"item_code": item["item_code"],
						"qty": mr["qty"],
						"rate": item["item_price"],
						"material_request": mr["parent"],
						"material_request_item": mr["mritem"]
					})
			item['to_order'] = item['qty_to_order'] - item['mr_total_qty']
			if item['to_order'] > 0:
				doc.append("items", {
					"item_code": item["item_code"],
					"qty": item["to_order"]
				})
	doc.save()
	return doc
