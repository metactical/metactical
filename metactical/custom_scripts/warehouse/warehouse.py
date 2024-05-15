import frappe
from frappe.utils.xlsxutils import make_xlsx
from frappe.utils.background_jobs import enqueue

@frappe.whitelist()
def export_to_excel(warehouse):
	enqueue(export_inventory, warehouse=warehouse, timeout=2000)

def export_inventory(warehouse):
	try:
		frappe.publish_realtime("msgprint", "Export started in the background ...", user=frappe.session.user)

		bins = frappe.db.sql("""
			SELECT 
				ifw_retailskusuffix as retail_sku, item_name, actual_qty, reserved_qty, `tabBin`.item_code
			FROM 
				`tabBin`
				join `tabItem` on `tabItem`.item_code = `tabBin`.item_code
			WHERE 
				warehouse = %s
		""", warehouse, as_dict=1)

		data = [["Retail SKU", "Item Name", "QOH", "Cost", "Supplier SKU"]]

		for d in bins:
			# default supplier 
			supplier = frappe.db.get_list("Item Supplier", {"parent": d.get("item_code")}, ["supplier", "supplier_part_no"], limit=1, order_by="idx asc")
			if supplier:
				item_cost = get_item_details(d.get("item_code"), supplier=supplier[0].get("supplier"))
				data.append([d.retail_sku, d.item_name, d.actual_qty - d.reserved_qty, item_cost, supplier[0].get("supplier_part_no")])
			else:
				data.append([d.retail_sku, d.item_name, d.actual_qty - d.reserved_qty, "N/A", "N/A"])

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