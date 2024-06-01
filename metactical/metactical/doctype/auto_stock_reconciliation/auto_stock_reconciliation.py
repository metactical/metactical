# Copyright (c) 2024, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
import os
from frappe.utils.xlsxutils import read_xlsx_file_from_attached_file, read_xls_file_from_attached_file

class AutoStockReconciliation(Document):
	def on_submit(self):
		file_content = self.check_file()
		self.create_reconciliation(file_content)
	
	def read_file(self):
		file_path = self.excel_file
		extn = os.path.splitext(file_path)[1][1:]

		file_content = None

		file_name = frappe.db.get_value("File", {"file_url": file_path})
		if file_name:
			file = frappe.get_doc("File", file_name)
			file_content = file.get_content()

		return file_content, extn

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

	def create_reconciliation(self, data):
		limit = 99
		start = 0
		while start < len(data):
			end = start + limit
			self.create_reconciliation_entries(data[start:end])
			start = end

	def create_reconciliation_entries(self, data):
		doc = frappe.new_doc("Stock Reconciliation")
		doc.purpose = "Stock Reconciliation"
		doc.ais_reason_for_adjustment = self.reason_for_adjustment
		for row in data:
			if row[0] == "Retail SKU":
				continue

			item_code = frappe.db.get_value("Item", {"ifw_retailskusuffix": row[0]}, "item_code")
			if item_code is not None and item_code != "":
				doc.append("items", {
					"item_code": item_code,
					"warehouse": self.warehouse,
					"qty": 0
				})

		if hasattr(doc, "items"):
			try:
				doc.submit()
			except Exception as e:
				frappe.msgprint(frappe.get_traceback())