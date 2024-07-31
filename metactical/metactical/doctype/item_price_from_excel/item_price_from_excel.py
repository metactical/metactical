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
		self.create_price_entries(file_content)

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

	def create_price_entries(self, data, external_source=False):
		item_code_col = None
		item_sku_col = None
		price_lists = []

		for col in data[0]:
			if col in ["ItemCode", "ERPSKU"]:
				item_code_col = data[0].index(col)
			elif col in ["Retail SKU"]:
				item_sku_col = data[0].index(col)
			else:
				# Check if it's a price list
				price_list = frappe.db.exists("Price List", {"name": col})
				if price_list:
					price_lists.append(col)
					
		if price_lists == []:
			frappe.throw("No price list found in the file")

		for row in data[1:]:
			item_code = None
			item_sku = None

			if item_code_col is not None:
				item_code = row[item_code_col]

			if item_sku_col is not None:
				item_sku = row[item_sku_col]
			
			for price_list in price_lists:
				price = row[data[0].index(price_list)]
				if item_code is not None and item_code != "" and self.import_based_on == "ERP SKU":
					exists = frappe.db.exists("Item Price", {"item_code": item_code, "price_list": price_list})
				elif item_sku is not None and item_sku != "" and self.import_based_on == "Retail SKU":
					item_code = frappe.db.get_value("Item", {"ifw_retailskusuffix": item_sku}, "name")
					query = frappe.db.sql("""SELECT 
						   						item_price.name
						   					FROM 
						   						`tabItem Price` item_price
						   					LEFT JOIN
						   						`tabItem` AS item ON item.name = item_price.item_code
						   					WHERE
						   						item.ifw_retailskusuffix = %(item_sku)s AND item_price.price_list = %(price_list)s""", 
											{"item_sku": item_sku, "price_list": price_list}, as_dict=1)
					if query and len(query) > 0:
						exists = query[0]["name"]
					else:
						exists = False
						
				if not self.replace_existing and exists:
					continue
				elif item_code is None or item_code == "":
					continue
				else:
					if exists:
						doc = frappe.get_doc("Item Price", exists)
					else:
						doc = frappe.new_doc("Item Price")
					
					if not price and external_source:
						continue

					doc.update({
						"item_code": item_code,
						"price_list": price_list,
						"price_list_rate": price,
					})
					try:
						doc.save()
					except Exception as e:
						frappe.log_error(frappe.get_traceback())
						error_log = frappe.new_doc("Item Price From Excel Error")
						error_log.update({
							"error": e,
							"item_code": item_code,
							"rate": price,
							"parenttype": self.doctype,
							"parent": self.name,
							"parentfield": "error_log"
						})
						error_log.insert()
