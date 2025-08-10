# Copyright (c) 2025, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from metactical.custom_scripts.utils.orders_api import re_sync_rmq_order

class RabbitMQOrdersLog(Document):
    pass

@frappe.whitelist()
def re_sync_order(order_id):
	"""Re-sync orders from RabbitMQ"""
	re_sync_rmq_order(order_id)