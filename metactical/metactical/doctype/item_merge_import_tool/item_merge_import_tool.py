# Copyright (c) 2025, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _, msgprint
from frappe.model.document import Document
from frappe.utils.xlsxutils import read_xlsx_file_from_attached_file, read_xls_file_from_attached_file
from frappe.model.docstatus import DocStatus
from frappe.model.rename_doc import rename_doc
from frappe.utils.file_manager import save_file
from metactical.custom_scripts.utils.metactical_utils import queue_action
import os


class ItemMergeImportTool(Document):
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
			queue_action(self, "submit", timeout=2000)
		else:
			super().save()

  
	def on_submit(self):
		file_content = self.check_file()
		self.merge_items(file_content)

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
		file_content = self.check_file()
		self.check_headers(file_content)
		row_no = 1
		rows = file_content[1:]
		for template in rows:
			if (template[1]) or (not template[0]):
				continue		
   
			item = frappe.db.exists("Item", template)
			if not item:
				frappe.throw(f"Item '{template}' does not exist in the system.")
    
			item = frappe.get_doc("Item", item)
			if row_no == 1:
				if not item.has_variants:
					frappe.throw(f"Item '{template}' is not a template item.")
			else:
				if item.has_variants:
					frappe.throw(f"Item '{template}' is a template item. Only variant items are allowed.")
			row_no += 1

	def check_file(self):
		file_content, extn = self.read_file()
		if extn == "xlsx":
			file_content = read_xlsx_file_from_attached_file(fcontent=file_content)
		elif extn == "xls":
			file_content = read_xls_file_from_attached_file(file_content)
		else:
			frappe.throw("Only xls and xlsx files are supported.")
		return file_content
	
	def check_headers(self, file_content):
		expected_headers = ["Current SKU", "New SKU"]

		for header in file_content[0]:
			if header not in expected_headers:
				frappe.throw(f"Header '{header}' should not be in this Excel File.")

	def merge_items(self, data):
		limit = 500
		start = 0
		while start < len(data):
			end = start + limit
			self._merge_items(data[start:end])
			start = end

	def _merge_items(self, data):
		for i, row in enumerate(data):
			if row[0] == "Current SKU":
				continue

			current_sku = row[0]
			new_sku = row[1]
   
			if current_sku == new_sku:
				continue
   
			item_inventory_output = frappe.db.exists("Item Inventory Output", new_sku)
			if item_inventory_output:
				frappe.delete_doc("Item Inventory Output", item_inventory_output)

			rename_doc(
				doctype="Item",
				old=current_sku,
				new=new_sku,
				merge=True,
			)
			frappe.db.commit()