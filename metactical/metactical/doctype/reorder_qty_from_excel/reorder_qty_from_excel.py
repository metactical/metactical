# Copyright (c) 2025, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
import os
from frappe.utils import flt
from frappe import _
from frappe.utils.xlsxutils import read_xlsx_file_from_attached_file, read_xls_file_from_attached_file
from metactical.custom_scripts.utils.metactical_utils import queue_action
from frappe.utils.xlsxutils import make_xlsx
from frappe import _, msgprint
from frappe.model.docstatus import DocStatus

class ReorderQtyFromExcel(Document):
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
			queue_action(self, "submit", timeout=3600)
		else:
			super().save()
	
	def validate(self):
		file_content = self.check_file()
		headers = [
			self.import_based_on, "Item Name", "Months to Block Reorder",
			"Check in (group)", "Request for", "Re-order Level",
			"Re-order Qty", "Material Request Type", "Delete Row"
		]

		for header in headers:
			if header not in file_content[0]:
				frappe.throw(f"Column <b>{header}</b> is missing")
		self.check_mandatory(file_content)

	def on_submit(self):
		file_content = self.check_file()
		self.check_mandatory(file_content)
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
		extn = os.path.splitext(file_path)[1][1:]  # extension without dot

		file_name = frappe.db.get_value("File", {"file_url": file_path}, "name")
		if not file_name:
			frappe.throw("Attached file not found.")

		file = frappe.get_doc("File", file_name)
		file_content = file.get_content()

		return file_content, extn

	def update_items(self, data):
		header = data[0]
		indexes = self.get_column_indexes(header)
		errors = []
		items = []

		for i, row in enumerate(data[1:], start=2):
			if not any(row):
				continue

			try:
				if "ERP SKU" == header[0]:
					item_code = row[0]
				else:
					retail_code = row[0]
					item_code = frappe.db.get_value("Item", {"ifw_retailskusuffix": retail_code}, "name")

				if not item_code:
					frappe.msgprint(f"Row {i}: Item not found")
					continue

				warehouse_group = row[indexes["check_in_group"]]
				if warehouse_group not in (None, "", "None"):
					warehouse_group = str(warehouse_group)
					self.validate_warehouse_group(warehouse_group, is_group=True)

				warehouse = str(row[indexes["request_for"]])
				self.validate_warehouse_group(warehouse, is_group=False)

				level = str(row[indexes["reorder_level"]])
				qty = str(row[indexes["reorder_qty"]])
				mr_type = str(row[indexes["material_request_type"]])
	
				delete_row = str(row[indexes["delete_row"]] or "0").strip()
				self.validate_delete_row(delete_row)

				reorder_exists = frappe.db.exists("Item Reorder", 
									  	{
										  "parent": item_code,
										  "warehouse": warehouse,
										  "material_request_type": mr_type
										}
									)
				if delete_row == "0":
					if reorder_exists:
						reorder_level = frappe.get_doc("Item Reorder", reorder_exists)
						reorder_level.warehouse_group = warehouse_group
						reorder_level.warehouse = warehouse
						reorder_level.warehouse_reorder_level = flt(level)
						reorder_level.warehouse_reorder_qty = flt(qty)
						reorder_level.material_request_type = mr_type
						reorder_level.save()
						frappe.db.commit()
					else:
						reorder_level = frappe.get_doc({
		  					"doctype": "Item Reorder",
							"parent": item_code,
							"parenttype": "Item",
							"parentfield": "reorder_levels",
							"warehouse_group": warehouse_group,
	   						"warehouse": warehouse,
			 				"warehouse_reorder_level": flt(level),
							"warehouse_reorder_qty": flt(qty),
	   						"material_request_type": mr_type
				 		})
						reorder_level.insert()
						frappe.db.commit()
				else:
					if reorder_exists:
						frappe.db.delete("Item Reorder", reorder_exists)
						frappe.db.commit()
	
				item = frappe.get_doc("Item", item_code)
				
				months_to_reorder = [m.strip() for m in str(row[indexes["months_to_block_reorder"]]).split(",") if m]
				if  len(item.reorder_levels) <= 1:
					months_list_to_delete_exists = frappe.db.exists("Months List", {
									"parent": item_code,
									"parenttype": "Item",
									"parentfield": "months_to_reorder"
								})
					if months_list_to_delete_exists:
						months_list_to_delete = frappe.get_all("Months List", {
										"parent": item_code,
										"parenttype": "Item",
										"parentfield": "months_to_reorder"
									})
						for month_list_to_delete in months_list_to_delete:
							frappe.db.delete("Months List", month_list_to_delete)
						
				else:
					for month in months_to_reorder:
						if frappe.db.exists("Month", month):
							months_list_exists = frappe.db.exists("Months List", {
								"parent": item_code,
								"parenttype": "Item",
								"parentfield": "months_to_reorder",
								"month": month
							})
							if not months_list_exists:
								months_list = frappe.get_doc({
									"doctype": "Months List",
									"parent": item_code,
									"parenttype": "Item",
									"parentfield": "months_to_reorder",
									"month": month
								})
								months_list.insert()
								frappe.db.commit()
						else:
							frappe.throw(f"Month '{month}' does not exist.")

				frappe.db.commit()

			except Exception as e:
				frappe.clear_messages()
				errors.append(f"Row {i}: {str(e)}")
	
		if errors:
			frappe.db.rollback()
			error_message = "<br>".join(errors)
			frappe.throw(f"Errors encountered:<br>{error_message}")
		else:
			for item in items:
				try:
					frappe.flags.in_test = True
					item.save()
				except Exception as e:
					frappe.clear_messages()
					frappe.db.rollback()
					frappe.throw(f"Error saving item {item.name}: {str(e)}")
	 
	def validate_delete_row(self, delete_row):
		delete_row = str(delete_row)
		if str(delete_row.lower()) not in ["1", "0"]:
			frappe.throw(f"Invalid value '{delete_row}' in 'Delete Row' column. Use '1' for True and '0' for False.")
	 
	def validate_warehouse_group(self, warehouse_group, is_group):
		if is_group:
			warehouse_group = frappe.db.get_value("Warehouse", warehouse_group, ["name", "is_group"], as_dict=1)
			if not warehouse_group:
				frappe.throw(f"Warehouse Group '{warehouse_group}' does not exist.")
			if warehouse_group and warehouse_group.is_group != 1:
				frappe.throw(f"'{warehouse_group}' is not a Warehouse Group.")
		else:
			warehouse_detail = frappe.db.get_value("Warehouse", warehouse_group, ["name", "is_group"], as_dict=1)

			if not warehouse_detail:
				frappe.throw(f"Warehouse '{warehouse_group}' does not exist.")
			if warehouse_detail and warehouse_detail.is_group == 1:
				frappe.throw(f"'{warehouse_group}' is a Warehouse Group, not a Warehouse.")
						   
						   
	def check_mandatory(self, data):
		header = data[0]
		indexes = self.get_column_indexes(header).values()

		if self.import_based_on not in header:
			frappe.throw(f"Column <b>{self.import_based_on}</b> is missing")

		for i, data in enumerate(data[1:]):
			# continue if all the columns in the row are empty
			if not any(data):
				continue
			
			for index in indexes:
				if (data[index] == "" or data[index] == None) and header[index] not in ["Months to Block Reorder", "Check in (group)", "Delete Row"]:
					frappe.throw(f"Column <b>{header[index]}</b> is mandatory in row {i+2}")


	
	def get_column_indexes(self, header):
		"""
		Map each column header to its index for easy access in rows.
		"""
		indexes = {}
		for i, col in enumerate(header):
			if not col:
				continue

			if col == self.import_based_on:
				indexes["sku"] = i
			elif col == "Item Name":
				indexes["item_name"] = i
			elif col == "Months to Block Reorder":
				indexes["months_to_block_reorder"] = i
			elif col == "Check in (group)":
				indexes["check_in_group"] = i
			elif col == "Request for":
				indexes["request_for"] = i
			elif col == "Re-order Level":
				indexes["reorder_level"] = i
			elif col == "Re-order Qty":
				indexes["reorder_qty"] = i
			elif col == "Material Request Type":
				indexes["material_request_type"] = i
			elif col == "Delete Row":
				indexes["delete_row"] = i
		return indexes


	# @frappe.whitelist()
	# def get_preview_from_template(doc):
	# 	"""
	# 	Return the first 10 rows of the uploaded excel as preview with column headers.
	# 	"""
	# 	doc = frappe.get_doc("Reorder Qty From Excel", doc.name)

	# 	if not doc.excel_file:
	# 		return

	# 	file_content = doc.check_file()
	# 	if not file_content:
	# 		return

	# 	header = file_content[0]
	# 	data = file_content[1:11]  # first 10 rows only

	# 	preview_rows = []
	# 	for row in data:
	# 		if any(row):
	# 			preview_rows.append(row)

	# 	return {
	# 		"columns": header,
	# 		"data": preview_rows
	# 	}


@frappe.whitelist()
def download_template(export_type, import_based_on="ERP SKU"):
	# Define column headers for the Excel file
	columns_list = [
		[
			import_based_on, "Item Name", "Months to Block Reorder", "Check in (group)", "Request for", "Re-order Level", "Re-order Qty", "Material Request Type", "Delete Row"
		]
	]
	data_list = []

	# Fetch data based on export type
	if export_type != "Blank":
		data = frappe.get_all("Item")

		# Build data rows
		for d in data:
			item = frappe.get_doc("Item", d.name)
			item_identifier = item.item_code if import_based_on == "ERP SKU" else item.ifw_retailskusuffix
			months_to_block_reorder = []

			if item.months_to_reorder:
				for month in item.months_to_reorder:
					months_to_block_reorder.append(month.month)
			if item.reorder_levels:
				for reorder_level in item.reorder_levels:
					row = [
						item_identifier, 
						item.item_name, 
						','.join(months_to_block_reorder), 
						str(reorder_level.warehouse_group), 
						str(reorder_level.warehouse),
						str(reorder_level.warehouse_reorder_level),
						str(reorder_level.warehouse_reorder_qty),
						str(reorder_level.material_request_type),
						"0"
					]
					data_list.append(row)

	# Combine headers and data
	full_data = columns_list + data_list

	# Generate XLSX file content
	xlsx_file = make_xlsx(full_data, "excel_data").getvalue()

	# Update response with file data
	frappe.local.response.update({
		"filecontent": xlsx_file,
		"type": "binary",
		"filename": "Reorder Qty Template.xlsx"
	})
 