import frappe
import requests

def get_context(context):
	context.no_cache = 1
	search_text = frappe.request.args["searchtext"]
	context.csrf_token = frappe.sessions.get_csrf_token()
	context.columns = get_columns()
	context.data = get_data(search_text)

def get_columns():
	columns = [
		{
			"fieldname": "retail_sku",
			"label": "RetailSKU"
		},
		{
			"fieldname": "item_name",
			"label": "Item Name"
		},
		{
			"fieldname": "WHSQOH",
			"label": "WHSQOH"
		}
	]

	franchises = frappe.db.get_all("Item Search Settings Franchise", fields=["label"])
	for franchise in franchises:
		columns.append({
			"fieldname": franchise.label,
			"label": franchise.label
		})

	columns.extend([
		{
			"fieldname": "barcode",
			"label": "Barcode"
		},
		{
			"fieldname": "ifw_location",
			"label": "IFW_Location"
		},
		{
			"fieldname": "item_code",
			"label": "Item Code"
		},
		{
			"fieldname": "template_sku",
			"label": "ERPNextTemplateSKU"
		}
	])
	return columns

def get_data(search_text):
	data = []
	franchises = frappe.db.get_all("Item Search Settings Franchise", fields=["franchise_url", "label", "api_key", "api_secret"])

	if not franchises:
		frappe.throw("No Franchise settings found. Please create a Franchise setting first.")

	local_data = get_local(search_text)

	if len(local_data) > 0:
		data.append({
			"label": "WHSQOH",
			"items": local_data
		})

	for franchise in franchises:
		url = franchise.franchise_url
		label = franchise.label
		api_key = franchise.api_key
		api_secret = franchise.api_secret

		if not url or not label or not api_key or not api_secret:
			frappe.throw("Franchise settings are incomplete. Please fill all the fields in the Franchise setting.")

		franchise_data = requests.get(f"{url}/api/method/metactical.api.stock_balance.get_total_items", 
							params={"search_text": search_text}, auth=(api_key, api_secret))
		
		if franchise_data.status_code == 200:
			data.append({
				"label": label,
				"items": franchise_data.json().get("message", [])
			})

	ret_data = {}
	# Merge data from all franchises into a list of dicts of the format 
	# {"item_code": item_code, "item_name: item_name, "label": actual_qty}
	# where label is the name of the franchise
	for row in data:
		for item in row["items"]:
			if not ret_data.get(item["item_code"]):
				ret_data[item["item_code"]] = {
					"item_code": item["item_code"],
					"item_name": item.get("item_name"),
					"retail_sku": item.get("retail_sku"),
					"template_sku": item.get("template_sku", ""),
					"barcode": item.get("barcode"),
					"ifw_location": item.get("ifw_location"),
					row["label"]: int(item.get("actual_qty", 0))
				}
			else:
				ret_data[item["item_code"]][row["label"]] = int(item.get("actual_qty", 0))

	data = []
	for key in ret_data:
		data.append(ret_data[key])
	return data

def get_local(search_text):
	data =  frappe.db.sql(f"""
			SELECT
				bin.item_code, item.item_name, SUM(bin.actual_qty) AS actual_qty,
				item.ifw_retailskusuffix AS retail_sku, item.ifw_location,
				barcode_grouped.barcodes AS barcode,
				item.variant_of AS template_sku
			FROM 
				`tabBin` AS bin
			LEFT JOIN
				`tabItem` AS item ON item.item_code = bin.item_code
			LEFT JOIN
				(
					SELECT parent, GROUP_CONCAT(DISTINCT barcode SEPARATOR '<br>') AS barcodes
					FROM `tabItem Barcode`
					GROUP BY parent
				) AS barcode_grouped ON barcode_grouped.parent = item.name 
			WHERE
				bin.warehouse = 'W01-WHS-Active Stock - ICL' AND (barcode_grouped.barcodes LIKE '%{search_text}%' or 
				item.ifw_retailskusuffix like '%{search_text}%') AND item.disabled = 0
				AND item.has_variants = 0 AND item.is_sales_item = 1
			GROUP BY
				item_code, item_name, retail_sku, template_sku, ifw_location
			""", as_dict=1)
	return data