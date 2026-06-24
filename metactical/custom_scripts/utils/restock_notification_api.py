import frappe

def process_rmq_data(parsedContent):
	try:
		create_rmq_log(parsedContent)
		
	except Exception as e:
		frappe.log_error(title='Restock Subscription Log', message=frappe.get_traceback())
  
def create_rmq_log(parsedContent):
	try:
		publisher_site = parsedContent.get("publisher_site", "Unknown")	
		rmq_log = frappe.get_doc({
			"doctype": "Restock Subscription Log",
			"payload": as_unicode(parsedContent),
			"lead_source": publisher_site
		})
  
		rmq_log.insert()		
		frappe.db.commit()
  
	except Exception as e:
		frappe.log_error(title='Restock Subscription Log Creation Error', message=frappe.get_traceback())

def as_unicode(text: str, encoding: str = "utf-8") -> str:
	"""Convert to unicode if required"""
	if isinstance(text, str):
		return text
	elif text is None:
		return ""
	elif isinstance(text, bytes):
		return str(text, encoding)
	else:
		return str(text)