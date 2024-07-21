# Copyright (c) 2024, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
import os
from frappe.model.document import Document
from frappe.utils.xlsxutils import read_xlsx_file_from_attached_file, read_xls_file_from_attached_file
from metactical.custom_scripts.utils.metactical_utils import queue_action

class PurchaseOrderImportTool(Document):
	def submit(self):
		frappe.msgprint(
			"""The task has been enqueued as a background job. In case there is any issue on processing in background, 
			the system will add a comment about the error on this document and revert to the Draft stage"""
		)
		queue_action(self, "submit", timeout=2000)

	def on_submit(self):
		file_content = self.check_file()
		self.create_purchase_orders(file_content)

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

		if self.import_based_on == "ERP SKU":
			self.item_code_col = file_content[0].index('ERP SKU')

			# Suppor bith ERP SKU and ERPSKU
			if self.item_code_col is None:
				self.item_code_col = file_content[0].index('ERPSKU')

			if self.item_code_col is None:
				frappe.throw("ERP SKU column is required in excel file. Please make sure the column name is 'ERP SKU' or 'ERPSKU'")

		elif self.import_based_on == "Retail SKU":
			self.item_sku_col = file_content[0].index('Retail SKU')
			if self.item_sku_col is None:
				frappe.throw("Retail SKU column is required in excel file. Please make sure the column name is 'Retail SKU'")
			
		self.quantity_col = file_content[0].index('Qty')
		self.rate_col = file_content[0].index('Rate')
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
	
	def create_purchase_orders(self, data):
		#enqueue(self.create_order_entries(data))
		limit = 500
		start = 1
		while start < len(data):
			end = start + limit
			self.create_order_entries(data[start:end])
			start = end

	def create_order_entries(self, data):
		doc = frappe.new_doc("Purchase Order")
		doc.update({
			"supplier": self.supplier,
			"company": self.company,
			"transaction_date": frappe.utils.now_datetime(),
			"shipping_address": self.shipping_address,
			"buying_price_list": self.buying_price_list,
			"currency": self.currency,
			"conversion_rate": self.conversion_rate,
			"buying_price_list": self.buying_price_list,
			"set_warehouse": self.warehouse
		})

		for row in data:
			if row[self.quantity_col] is None or int(row[self.quantity_col]) == 0:
				continue
			
			item_code = None
			if self.import_based_on == "ERP SKU":
				item_code = row[self.item_code_col]
			elif self.import_based_on == "Retail SKU":
				item_code = frappe.db.get_value("Item", {"ifw_retailskusuffix": row[self.item_sku_col]}, "item_code")

			if item_code is not None and item_code != "":
				doc.append("items", {
					"item_code": item_code,
					"qty": int(row[self.quantity_col]),
					"warehouse": self.warehouse,
					"rate": float(row[self.rate_col])
				})
			else:
				frappe.log_error("Item not found for SKU : " + row[self.item_sku_col])

		# Add taxes
		'''taxes = get_taxes_and_charges("Sales Taxes and Charges Template", self.taxes_and_charges)
		for tax in taxes:
			doc.append("taxes", tax)'''

		try:
			doc.save()
		except Exception as e:
			frappe.log_error(frappe.get_traceback())
