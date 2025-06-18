# Copyright (c) 2025, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
import os
from frappe.utils.xlsxutils import read_xlsx_file_from_attached_file, read_xls_file_from_attached_file
from frappe import _, msgprint
from metactical.custom_scripts.utils.metactical_utils import queue_action
from frappe.model.docstatus import DocStatus

class ItemClassImportTool(Document):
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
		self.edit_item_class(file_content)

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
	
	def edit_item_class(self, data):
		#enqueue(self.create_order_entries(data))
		limit = 500
		start = 0
		while start < len(data):
			end = start + limit
			self._edit_item_class(data[start:end])
			start = end

	def _edit_item_class(self, data):
		for row in data:
			if row[0] == "Item Code":
				continue

			item_code = row[0]
			exists = frappe.db.exists("Item", {"item_code": item_code})

			if exists:
				try:
					frappe.db.set_value("Item", exists, "asi_item_class", row[1])
					frappe.db.commit()
				except Exception as e:
					self.log_error(item_code, frappe.get_traceback())
					frappe.publish_realtime("msgprint", "Error inserting item class : " + str(e), user=frappe.session.user)

	def log_error(self, item_code, error):
		error_entry = {
			"item_code": item_code,
			"error": error
		}
		self.append("error_log", error_entry)
		self.save(ignore_permissions=True)