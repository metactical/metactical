import frappe
from frappe.utils import now_datetime


def process_rmq_data(parsedContent):
	try:
		create_rmq_log(parsedContent)

	except Exception as e:
		frappe.log_error(title='Restock Subscription Log', message=frappe.get_traceback())


def create_rmq_log(parsedContent):
	try:
		rmq_log = frappe.get_doc({
			"doctype": "Restock Subscription Log",
			"customer_name": parsedContent.get("CustomerName"),
			"customer_email": parsedContent.get("Email"),
			"retail_sku": parsedContent.get("RetailSkuSuffix"),
			"lead_source": parsedContent.get("publisher_site", "Unknown"),
			"item_price": parsedContent.get("ItemPrice"),
			"received_at": now_datetime(),
			"payload": as_unicode(parsedContent),
		})

		rmq_log.insert()
		rmq_log.submit()
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
