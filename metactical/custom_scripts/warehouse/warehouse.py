import frappe
from frappe.utils.xlsxutils import make_xlsx
from frappe.utils.background_jobs import enqueue

@frappe.whitelist()
def export_items_with_price_list(warehouse):
	enqueue(export_items_with_their_price_list_to_excel, warehouse=warehouse, timeout=2000)

def export_items_with_their_price_list_to_excel(warehouse):
	try:
		frappe.publish_realtime("msgprint", "Export started in the background ...", user=frappe.session.user)

		limit = 500
		start = 0
		bins = ["test"]

		# Retail sku | Item name | Supplier price list cost | Supplier price list currency | RET - Camo - FRN
		data = [["Retail SKU", "Item Name", "Supplier Price List Cost", "Supplier Price List Currency", "RET - CamoFRN - USD", "QOH"]]

		while len(bins) > 0:
			bins = frappe.db.sql("""
				SELECT 
					ifw_retailskusuffix as retail_sku, item_name, actual_qty, reserved_qty, `tabBin`.item_code, `tabItem`.name
				FROM 
					`tabBin`
					join `tabItem` on `tabItem`.item_code = `tabBin`.item_code
				WHERE 
					warehouse = %s and 
					(actual_qty - reserved_qty) > 0
				LIMIT %s OFFSET %s
			""", (warehouse, limit, start), as_dict=1)

			for d in bins:
				# default supplier 
				qty = d.get("actual_qty") - d.get("reserved_qty")
				suppliers = frappe.db.get_list("Item Supplier", {"parent": d.get("item_code")}, ["supplier", "supplier_part_no"], order_by="idx asc")
				item_cost = get_item_details2(d.get("item_code"), suppliers)

				if suppliers:
					data.append([d.retail_sku, d.item_name, item_cost[0], item_cost[1], item_cost[2], qty])
				else:
					data.append([d.retail_sku, d.item_name, "N/A", "N/A", item_cost[2], qty])

			start += limit

		xlsx_file = make_xlsx(data, warehouse + " inventory").getvalue()
		# save xlsx file
		xlsx = frappe.get_doc({
			"doctype": "File",
			"file_name": warehouse + " - ItemsWithRate.xlsx",
			"content": xlsx_file
		}).insert() 

		frappe.publish_realtime("msgprint", "Exported to Excel", user=frappe.session.user)
	except Exception as e:
		frappe.log_error(frappe.get_traceback())
		frappe.publish_realtime("msgprint", "Error exporting to Excel : " + str(e), user=frappe.session.user)

@frappe.whitelist()
def export_to_excel(warehouse):
	enqueue(export_inventory, warehouse=warehouse, timeout=2000)

def export_inventory(warehouse):
	try:
		frappe.publish_realtime("msgprint", "Export started in the background ...", user=frappe.session.user)

		bins = frappe.db.sql("""
			SELECT 
				ifw_retailskusuffix as retail_sku, item_name, actual_qty, reserved_qty, `tabBin`.item_code, `tabItem`.name
			FROM 
				`tabBin`
				join `tabItem` on `tabItem`.item_code = `tabBin`.item_code
			WHERE 
				warehouse = %s
		""", warehouse, as_dict=1)

		data = [["ERP SKU", "Retail SKU", "Item Name", "QOH", "Cost", "Supplier SKU"]]

		for d in bins:
			# default supplier 
			supplier = frappe.db.get_list("Item Supplier", {"parent": d.get("item_code")}, ["supplier", "supplier_part_no"], limit=1, order_by="idx asc")
			if supplier:
				item_cost = get_item_details(d.get("item_code"), supplier=supplier[0].get("supplier"))
				data.append([d.name, d.retail_sku, d.item_name, d.actual_qty - d.reserved_qty, item_cost, supplier[0].get("supplier_part_no")])
			else:
				data.append([d.name, d.retail_sku, d.item_name, d.actual_qty - d.reserved_qty, "N/A", "N/A"])

		xlsx_file = make_xlsx(data, warehouse + " inventory").getvalue()

		# save xlsx file
		xlsx = frappe.get_doc({
			"doctype": "File",
			"file_name": warehouse + " - Full Inventory.xlsx",
			"content": xlsx_file
		}).insert() 

		frappe.publish_realtime("msgprint", "Exported to Excel", user=frappe.session.user)
	except Exception as e:
		frappe.log_error(frappe.get_traceback())
		frappe.publish_realtime("msgprint", "Error exporting to Excel : " + str(e), user=frappe.session.user)

def get_item_details(item, supplier=None):
	# get price list for the supplier
	price_list = frappe.db.get_value("Supplier", supplier, "default_price_list")
	if not price_list:
		price_list = "Standard Buying"

	rate = frappe.db.get_value("Item Price", {"item_code": item, "price_list": price_list, "buying": 1}, 'price_list_rate')
	if not rate:
		return "N/A"
	return rate

def get_item_details2(item, suppliers=None):
	min_rate = "N/A"
	min_rate_supplier = "N/A"
	currency = "N/A"
	suppliers_list = [supplier.get("supplier") for supplier in suppliers]

	if suppliers:
		# get price list for the supplier
		for supplier in suppliers:
			supplier = supplier.get("supplier")
			price_list = frappe.db.get_value("Supplier", supplier, "default_price_list")
			if not price_list:
				price_list = "Standard Buying"

			item_price = frappe.db.get_values("Item Price", 
													filters={"item_code": item, "price_list": price_list, "buying": 1}, 
													fieldname=["name", "price_list_rate", "currency"],
													as_dict=True
												)

			if not item_price:
				continue
			
			if "(Default Supplier)" in suppliers_list or "Default Supplier" in suppliers_list:
				min_rate = item_price[0].get("price_list_rate")
				currency = item_price[0].get("currency")
				min_rate_supplier = supplier
				break
			else:
				if min_rate == "N/A" or not min_rate:
					min_rate = item_price[0].get("price_list_rate")
					min_rate_supplier = supplier
					currency = item_price[0].get("currency")
				elif item_price[0].get("price_list_rate") and item_price[0].get("price_list_rate") < min_rate:
					min_rate = item_price[0].get("price_list_rate")
					min_rate_supplier = supplier
					currency = item_price[0].get("currency")

	camo_frn_price = frappe.db.get_value("Item Price", {"item_code": item, "price_list": "RET - CamoFRN - USD"}, "price_list_rate")
	if not camo_frn_price:
		camo_frn_price = "N/A"
	
	if not min_rate and not currency:
		return "N/A", "N/A", camo_frn_price
	return min_rate, currency, camo_frn_price
