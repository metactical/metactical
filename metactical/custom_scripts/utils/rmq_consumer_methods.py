import frappe

def receive_item_price(parsedContent):
	try:
		# get the file path
		item_code = parsedContent.get("item_code")
		price_list_rate = parsedContent.get("price_list_rate")
		price_list = parsedContent.get("price_list")
		currency = parsedContent.get("currency") 
		valid_from = parsedContent.get("valid_from") or ""
		valid_to = parsedContent.get("valid_to") or ""
		uom = parsedContent.get("uom") if parsedContent.get('uom') != "None" else ""

		item_price = frappe.db.exists("Item Price", {"item_code": item_code, "price_list": price_list})
		item_price_obj = {
			"item_code": item_code,
			"price_list": price_list,
			"price_list_rate": price_list_rate,
			"currency": currency,
			"uom": uom,
			"valid_from": valid_from,
			"valid_to": valid_to
		}

		if item_price:
			item_price = frappe.get_doc("Item Price", item_price)
			item_price.update(item_price_obj)
			item_price.save()
		else:
			item_price_obj.update({"doctype": "Item Price"})
			item_price = frappe.get_doc(item_price_obj).insert()

		frappe.db.commit()
	except Exception as e:
		message = ""
		if parsedContent:
			message = f"Item: {parsedContent.get('item_code')} \n Price List: {parsedContent.get('price_list')} \n Price: {parsedContent.get('price_list_rate')} \n Currency: {parsedContent.get('currency')} \n UOM: {parsedContent.get('uom')} \n Valid From: {parsedContent.get('valid_from')} \n Valid To: {parsedContent.get('valid_to')}"
   
		message += f"\n Error: {str(e)}"
		frappe.log_error(title="Item Price Error", message=message)