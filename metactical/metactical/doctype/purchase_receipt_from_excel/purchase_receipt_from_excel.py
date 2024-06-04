# Copyright (c) 2024, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
import os
from frappe.utils.xlsxutils import read_xlsx_file_from_attached_file, read_xls_file_from_attached_file

class PurchaseReceiptFromExcel(Document):
	def on_submit(self):
		file_content = self.check_file()
		self.create_purchase_receipt(file_content)

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

	def create_purchase_receipt(self, data):
		#enqueue(self.create_order_entries(data))
		limit = 500
		start = 0
		while start < len(data):
			end = start + limit
			self.create_receipt_entries(data[start:end])
			start = end

	def create_receipt_entries(self, data):
		doc = frappe.new_doc("Purchase Receipt")
		doc.update({
			"supplier": self.supplier,
			"set_warehouse": self.warehouse,
			"ignore_pricing_rule": 1,
			"base_grand_total": 0,
			"grand_total": 0,
			"rounded_total": 0,
			"currency": "CAD",
		})
		for row in data:
			if row[0] == "Item Code" or row[2] is None:
				continue

			if int(row[2]) == 0:
				continue

			item_code = row[0]
			if item_code is not None and item_code != "":
				doc.append("items", {
					"item_code": item_code,
					"item_name": row[1],
					"warehouse": self.warehouse,
					"qty": int(row[2]),
					"rate": int(row[3])
				})
		try:
			doc.save()
		except Exception as e:
			frappe.log_error(frappe.get_traceback())
			frappe.publish_realtime("msgprint", "Error creating purchase receipt : " + str(e), user=frappe.session.user)
