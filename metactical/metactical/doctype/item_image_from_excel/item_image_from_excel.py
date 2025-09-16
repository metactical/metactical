# Copyright (c) 2024, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
import os
import datetime
from frappe import _
from frappe.utils.xlsxutils import read_xlsx_file_from_attached_file, read_xls_file_from_attached_file
from metactical.custom_scripts.utils.metactical_utils import queue_action
from frappe.utils.xlsxutils import make_xlsx
from metactical.metactical.report.pricing_rule_report___v1.pricing_rule_report___v1 import execute
from frappe import _, msgprint
from frappe.model.docstatus import DocStatus

class ItemImageFromExcel(Document):
	def save(self):
		if self.docstatus == DocStatus.submitted() and \
			self.ais_queue_status and self.ais_queue_status != "Queued":
			msgprint(
				_(
					"The task has been enqueued as a background job. In case there is \
					any issue on processing in background, the system will add a comment \
					about the error on this document and revert to the Draft stage"
				)
			)
			queue_action(self, "submit", timeout=4000)
		else:
			super().save()
	
	def validate(self):
		file_content = self.check_file()
  
		headers = [h.replace(" ", "").lower() for h in file_content[0] if h]
  
		if self.import_based_on.replace(" ", "").lower() not in headers:
			frappe.throw(f"Column '{self.import_based_on}' is mandatory")
   
		if "imagelinks" not in headers:
			frappe.throw(f"Column 'Image Links' is mandatory")
       
	def on_submit(self):
		file_content = self.check_file()
		self.update_items(file_content)

	def check_file(self):
		file_content, extn = self.read_file()
		if extn == "xlsx":
			file_content = read_xlsx_file_from_attached_file(fcontent=file_content)
		elif extn == "xls":
			file_content = read_xls_file_from_attached_file(file_content)
		else:
			frappe.throw("Only xls and xlsx files are supported.")

		cleaned_data = []
		# Remove empty rows
		for row in file_content:
			if any(row):
				cleaned_data.append(row)
				
		return cleaned_data
	
	def read_file(self):
		file_path = self.excel_file
		extn = os.path.splitext(file_path)[1][1:]

		file_content = None

		file_name = frappe.db.get_value("File", {"file_url": file_path})
		if file_name:
			file = frappe.get_doc("File", file_name)
			file_content = file.get_content()

		return file_content, extn

	def update_items(self, file_content):
		batch_size = 1000
		items = []

		item_code_index = None
		retail_sku_index = None
  
		if self.import_based_on.replace(" ", "").lower() == "erpsku":
			item_code_index = self.get_column_indexes(file_content[0])["item_code"]
		elif self.import_based_on.replace(" ", "").lower() == "retailsku":
			retail_sku_index = self.get_column_indexes(file_content[0])["ifw_retailskusuffix"]
  
		image_index = self.get_column_indexes(file_content[0])["image"]
  
		for i, item in enumerate(file_content[1:]):
			# create a batch of items
			if self.import_based_on.replace(" ", "").lower() == "retailsku":	
				item_code = frappe.db.get_value("Item", {"ifw_retailskusuffix": item[retail_sku_index]}, "name")
				if item_code:
					items.append({
						"item": item_code,
						"image": item[image_index]
					})
			else:
				items.append({
					"item": item[item_code_index],
					"image": item[image_index]
				})

			if len(items) == batch_size or i == len(file_content[1:]) - 1:
				frappe.enqueue(
					self.update_items_image_link,
					job_name='update items image link',
					items=items,
					queue='default',
					timeout=300
				)
				items = []
				frappe.db.commit()
		
	def update_items_image_link(self, items):
		for item in items:
			frappe.db.set_value('Item', item["item"], 'image', item["image"], update_modified=False)
			
		frappe.db.commit()
			

	def get_column_indexes(self, header):
		indexes = {}
		for i, col in enumerate(header):
			if not col:
				continue

			if col.replace(" ", "").lower() == "erpsku":
				indexes["item_code"] = i
			elif col.replace(" ", "").lower() == "imagelinks":
				indexes["image"] = i
			elif col.replace(" ", "").lower() == "retailsku":
				indexes["ifw_retailskusuffix"] = i
	
		return indexes