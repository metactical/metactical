# Copyright (c) 2024, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
import os
from frappe.utils.xlsxutils import read_xlsx_file_from_attached_file, read_xls_file_from_attached_file
from metactical.custom_scripts.utils.metactical_utils import queue_action

class ItemPriceFromExcel(Document):
	def submit(self):
		frappe.msgprint(
			"""The task has been enqueued as a background job. In case there is any issue on processing in background, 
			the system will add a comment about the error on this document and revert to the Draft stage"""
		)
		queue_action(self, "submit", timeout=2000)

	def on_submit(self):
		file_content = self.check_file()
		self.create_item_prices(file_content)

	def validate(self):
		self.check_file()

	def check_file(self):
		file_content, extn = self.read_file()
		if extn == "xlsx":
			file_content = read_xlsx_file_from_attached_file(fcontent=file_content)
		elif extn == "xls":
			file_content = read_xls_file_from_attached_file(file_content)
		else:
			frappe.throw("Only xls and xlsx files are supported.")
		return file_content
	
	def read_file(self):
		file_path = self.excel_file
		extn = os.path.splitext(file_path)[1][1:]

		file_content = None

		file_name = frappe.db.get_value("File", {"file_url": file_path})
		if file_name:
			file = frappe.get_doc("File", file_name)
			file_content = file.get_content()

		return file_content, extn

	def create_item_prices(self, data):
		#enqueue(self.create_order_entries(data))
		limit = 500
		start = 0
		while start < len(data):
			end = start + limit
			self.create_price_entries(data[start:end])
			start = end

	def create_price_entries(self, data):
		for row in data:
			if row[0] == "ItemCode" or row[4] is None:
				continue
			
			item_code = row[0]
			exists = frappe.db.exists("Item Price", {"item_code": item_code, "price_list": self.price_list})
			if not self.replace_existing and exists:
				continue
			else:
				if item_code is not None and item_code != "":
					if exists:
						doc = frappe.get_doc("Item Price", exists)
					else:
						doc = frappe.new_doc("Item Price")
					doc.update({
						"item_code": item_code,
						"price_list": self.price_list,
						"price_list_rate": row[4],
					})
					try:
						doc.save()
					except Exception as e:
						frappe.log_error(frappe.get_traceback())