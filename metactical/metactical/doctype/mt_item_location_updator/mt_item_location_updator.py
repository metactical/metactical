# Copyright (c) 2024, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils.xlsxutils import read_xls_file_from_attached_file, read_xlsx_file_from_attached_file
from metactical.custom_scripts.utils.metactical_utils import queue_action, read_file

class MTItemLocationUpdator(Document):
	def validate(self):
		file_content = self.check_file()
		self.validate_file(file_content)

	def on_submit(self):
		file_content = self.check_file()
		data = self.validate_file(file_content, only_validate=False)

		try:
			for row in data:
				frappe.db.set_value("Item", row["item_code"], "ifw_location", row["location"])
			
			frappe.db.commit()
		except Exception as e:
			frappe.rollback()
			frappe.throw(f"Error updating Item: {e}")

	def submit(self):
		frappe.msgprint(
			"""The task has been enqueued as a background job. In case there is any issue on processing in background, 
			the system will add a comment about the error on this document and revert to the Draft stage"""
		)
		queue_action(self, "submit", timeout=2000)

	def validate_file(self, file_content, only_validate=True):
		header = file_content[0]
		item_code_index = -1
		location_index = -1
		
		data = []

		for i, col in enumerate(header):
			if col == self.import_based_on:
				item_code_index = i
			elif col == "Location":
				location_index = i

		if item_code_index == -1 or location_index == -1:
			frappe.throw(f"{self.import_based_on} and Location columns are required in the file.")
		
		for i, fcontent in enumerate(file_content[1:]):
			if fcontent[item_code_index]:
				if self.import_based_on == "Retail SKU":
					item_code = frappe.db.get_value("Item", {"ifw_retailskusuffix": fcontent[item_code_index]}, "name")
				else:
					item_code = fcontent[item_code_index]

				# check if the location is only include A-Z, a-z, 0-9, space and |
				if len(fcontent) > location_index:
					if fcontent[location_index] and not all(c.isalnum() or c.isspace() or c == "|" or c == "-" for c in fcontent[location_index]):
						frappe.throw(f"Location must only include A-Z, a-z, 0-9, space and | at row {i+2}")
				
				if only_validate:
					if self.import_based_on == "Retail SKU":
						if not item_code:
							frappe.throw(f"Item not found for Retail SKU {fcontent[item_code_index]} at row {i+2}")

					elif not frappe.db.exists("Item", item_code):
						frappe.throw(f"Item {item_code} not found at row {i+2}")

				data.append({
					"item_code": item_code,
					"location": fcontent[location_index] if len(fcontent) > location_index else None
				})
			else:
				frappe.throw(f"{self.import_based_on} and Location are required at row {i+2}")

		return data

	def check_file(self):
		file_content, extn = read_file(self.excel_file)
		if extn == "xlsx":
			file_content = read_xlsx_file_from_attached_file(fcontent=file_content)
		elif extn == "xls":
			file_content = read_xls_file_from_attached_file(file_content)
		else:
			frappe.throw("Only xls and xlsx files are supported.")
		
		# Cleaned data
		return file_content

# Function to remove rows with all None values
def remove_all_none_rows(data):
	return [[row for row in table if not all(value is None for value in row)] for table in data]

