import frappe

def receive_item_price(*args, **kwargs):
	try:
		# get the file path
		form_data = frappe.form_dict
		item_code = form_data.get("item_code")
		price_list_rate = form_data.get("price_list_rate")
		price_list = form_data.get("price_list")
		currency = form_data.get("currency")
		valid_from = form_data.get("valid_from")
		valid_to = form_data.get("valid_to")
		uom = form_data.get("uom")

		item_price = frappe.db.exists("Item Price", {"item_code": item_code, "price_list": price_list})
		if item_price:
			item_price = frappe.get_doc("Item Price", item_price)
			item_price.price_list_rate = price_list_rate
			item_price.currency = currency
			item_price.uom = uom
			item_price.valid_from = valid_from
			item_price.valid_to = valid_to
			item_price.save()
		else:
			item_price = frappe.get_doc({
				"doctype": "Item Price",
				"item_code": item_code,
				"price_list": price_list,
				"price_list_rate": price_list_rate,
				"currency": currency,
				"uom": uom,
				"valid_from": valid_from,
				"valid_to": valid_to
			}).insert()

		frappe.db.commit()
	except Exception as e:
		message = ""
		if form_data:
			message = f"Item: {form_data.get('item')} \n Price List: {form_data.get('price_list')} \n Price: {form_data.get('price_list_rate')} \n Currency: {form_data.get('currency')} \n UOM: {form_data.get('uom')} \n Valid From: {form_data.get('valid_from')} \n Valid To: {form_data.get('valid_to')}"
   
		message += f"\n Error: {str(e)}"
		frappe.log_error(title="Item Price Error", message=message)