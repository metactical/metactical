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

def get_data(search_text="rvx"):
	data = []
	franchises = frappe.db.get_all("Item Search Settings Franchise", fields=["franchise_url", "label", "api_key", "api_secret"])

	if not franchises:
		frappe.throw("No Franchise settings found. Please create a Franchise setting first.")

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
					row["label"]: item.get("actual_qty")
				}
			else:
				ret_data[item["item_code"]][row["label"]] = item["actual_qty"]

	data = []
	for key in ret_data:
		data.append(ret_data[key])
	return data