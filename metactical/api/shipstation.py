import frappe
from lxml import etree
from werkzeug.wrappers import Response

@frappe.whitelist(allow_guest=True)
def shipstation(action, start_date, end_date):
	if action and action == 'export':
		return return_orders(start_date, end_date)

@frappe.whitelist(allow_guest=True)
def return_orders(start_date, end_date):
	root = etree.Element("Orders")
	
	orders = get_orders(start_date, end_date)
	for row in orders:
		order = etree.SubElement(root, "Order")
		element = etree.SubElement(order, "OrderID")
		element.text = ctext(row.name)
		element = etree.SubElement(order, "OrderNumber")
		element.text = ctext(row.name)
		element = etree.SubElement(order, "OrderDate")
		element.text = row.transaction_date.strftime("%d/%m/%Y %H:%M %p")
		element = etree.SubElement(order, "OrderStatus")
		element.text = ctext(row.get("status", ""))
		element = etree.SubElement(order, "LastModified")
		element.text = row.modified.strftime("%d/%m/%Y %H:%M %p")
		element = etree.SubElement(order, "CurrencyCode")
		element.text = row.get("currency", "")
		element = etree.SubElement(order, "OrderTotal")
		element.text = str(row.get("grand_total"))
		element = etree.SubElement(order, "ShippingAmount")
		element.text = "0.0"
		
		#For customer
		croot = etree.SubElement(order, "Customer")
		element = etree.SubElement(croot, "CustomerCode")
		element.text = ctext(row.customer)
		
		#For billing info
		billName, billCompany, billPhone, billEmail = row.customer, '', '', ''
		address = {}
		if row.customer_address and row.customer_address is not None:
			address = frappe.get_doc("Address", row.customer_address)
			billPhone = ctext(address.get("phone", ""))
			billEmail = ctext(address.get("email_id", ""))
		else:
			#If there is no address break out of the loop to prevent sync errors
			root.remove(order)
			continue
			
		billTo = etree.SubElement(croot, "BillTo")
		element = etree.SubElement(billTo, "Name")
		element.text = billName
		element = etree.SubElement(billTo, "Phone")
		element.text = billPhone
		element = etree.SubElement(billTo, "Email")
		element.text = billEmail
		
		#For shipping. Otherwise use billing information
		shipName, shipCompany, shipAddress1, shipAddress2, shipCity = row.customer, '', '', '', ''
		shipState, shipPostalCode, shipCountry, shipPhone = '', '', '', ''
		if row.shipping_address_name and row.shipping_address_name is not None:
			shipping = frappe.get_doc("Address", row.shipping_address_name)
			shipAddress1 = ctext(shipping.get("address_line1", ""))
			shipAddress2 = ctext(shipping.get("address_line2", ""))
			shipCity = ctext(shipping.get("city", ""))
			shipState = ctext(shipping.get("state", ""))
			shipPostalCode = ctext(shipping.get("pincode", ""))
			shipPhone = ctext(shipping.get("phone", ""))
			#Get country code
			country = frappe.get_value("Country", shipping.country, "code")
			shipCountry = country
		elif row.customer_address is not None:
			shipAddress1 = ctext(address.get("address_line1", ""))
			shipAddress2 = ctext(address.get("address_line2", ""))
			shipCity = ctext(address.get("city", ""))
			shipState = ctext(address.get("state", ""))
			shipPostalCode = ctext(address.get("pincode", ""))
			shipPhone = ctext(address.get("phone", ""))
			#Get country code
			country = frappe.get_value("Country", address.country, "code")
			shipCountry = country
			
		shipTo = etree.SubElement(croot, "ShipTo")
		element = etree.SubElement(shipTo, "Name")
		element.text = shipName
		element = etree.SubElement(shipTo, "Company")
		element.text = shipCompany
		element = etree.SubElement(shipTo, "Address1")
		element.text = shipAddress1
		element = etree.SubElement(shipTo, "Address2")
		element.text = shipAddress2
		element = etree.SubElement(shipTo, "City")
		element.text = shipCity
		element = etree.SubElement(shipTo, "State")
		element.text = shipState
		element = etree.SubElement(shipTo, "PostalCode")
		element.text = shipPostalCode
		element = etree.SubElement(shipTo, "Country")
		element.text = shipCountry
		element = etree.SubElement(shipTo, "Phone")
		element.text = shipPhone
		
		#Get Items
		items = frappe.get_all("Sales Order Item", filters={"parent": row.name}, fields=['item_code', 'item_name', 'qty', 'rate'])
		iroot = etree.SubElement(order, "Items")
		for item in items:
			ritems = etree.SubElement(iroot, "Item")
			element = etree.SubElement(ritems, "SKU")
			element.text = ctext(item.get("item_code", ""))
			element = etree.SubElement(ritems, "Name")
			element.text = ctext(item.get("item_name", ""))
			element = etree.SubElement(ritems, "Quantity")
			element.text = str(int(item.get("qty", 0)))
			element = etree.SubElement(ritems, "UnitPrice")
			element.text = str(item.get("rate", 0))
		
	out = etree.tostring(root, pretty_print=True)
	
	#Log the request
	new_req = frappe.get_doc({
		"doctype": "Shipstation API Requests",
		"start_date": start_date,
		"end_date": end_date,
		"action": "Export",
		"result": out
	})
	new_req.insert(ignore_if_duplicate=True)
	
	response = Response()
	response.mimetype = "text/xml"
	response.charset = "utf-8"
	response.data = out
	return response


def ctext(txt):
	if txt is not None:
		return '<![CDATA[' + txt + ']]>'
	else:
		return ''
	
def get_orders(start_date, end_date):
	orders = frappe.get_all('Sales Order', fields=['name', 'transaction_date', 'status', 'modified', 'currency', 'grand_total', 'customer', 
									'customer_address', 'shipping_address_name'], 
									filters={"delivery_status": ("in", ("Not Delivered", "Partly Delivered")), "billing_status": "Fully Billed", 
									"modified": ("between", (start_date, end_date))})
	return orders
