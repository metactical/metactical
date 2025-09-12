# Copyright (c) 2025, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
import os
import datetime
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
		extn = os.path.splitext(file_path)[1][1:]

		file_content = None

		file_name = frappe.db.get_value("File", {"file_url": file_path})
		if file_name:
			file = frappe.get_doc("File", file_name)
			file_content = file.get_content()

		return file_content, extn

	def update_items(self, data):
		"""
		Loop through the uploaded rows and update Item master:
		- months_to_reorder child table
		- reorder_levels child table
		- delete row if requested
		"""
		header = data[0]
		indexes = self.get_column_indexes(header)

		for i, row in enumerate(data[1:], start=2):
			if not any(row):
				continue

			item_code, retail_sku, message = self.get_item_details(row, indexes)
			if message:
				frappe.msgprint(_("Row {0}: {1}").format(i, message))
				continue

			# skip row if user marked delete
			delete_flag = str(row[indexes["delete_row"]]).strip().lower()
			if delete_flag in ("true", "1", "yes"):
				frappe.delete_doc("Item", item_code, ignore_missing=True, force=True)
				continue

			item = frappe.get_doc("Item", item_code)

			# update months_to_reorder
			months_to_block = [m.strip() for m in str(row[indexes["months_to_block_reorder"]]).split(",") if m]
			item.set("months_to_reorder", [])
			for m in months_to_block:
				item.append("months_to_reorder", {"month": m})

			# update reorder_levels
			warehouses_group = [g.strip() for g in str(row[indexes["check_in_group"]]).split(",") if g]
			warehouses = [w.strip() for w in str(row[indexes["request_for"]]).split(",") if w]
			levels = [l.strip() for l in str(row[indexes["reorder_level"]]).split(",") if l]
			qtys = [q.strip() for q in str(row[indexes["reorder_qty"]]).split(",") if q]
			mr_types = [t.strip() for t in str(row[indexes["material_request_type"]]).split(",") if t]

			item.set("reorder_levels", [])
			for j in range(len(warehouses)):
				item.append("reorder_levels", {
					"warehouse_group": warehouses_group[j] if j < len(warehouses_group) else "",
					"warehouse": warehouses[j],
					"warehouse_reorder_level": levels[j] if j < len(levels) else 0,
					"warehouse_reorder_qty": qtys[j] if j < len(qtys) else 0,
					"material_request_type": mr_types[j] if j < len(mr_types) else ""
				})

			item.save()
		frappe.db.commit()

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
				if data[index] == "" or data[index] == None:
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


	def get_item_details(self, row, indexes):
		"""
		Return the item code and retail_sku from the given row
		depending on whether we import based on ERP SKU or Retail SKU.
		"""
		if self.import_based_on == "Retail SKU":
			retail_sku = row[indexes["sku"]]
			item_code = frappe.db.get_value("Item",
											{"ifw_retailskusuffix": retail_sku},
											"name")
		else:  # ERP SKU
			item_code = row[indexes["sku"]]
			retail_sku = frappe.db.get_value("Item",
											item_code,
											"ifw_retailskusuffix")

		if not item_code:
			if self.import_based_on == "Retail SKU":
				return None, None, _("Item with Retail SKU Suffix {0} not found").format(retail_sku)
			else:
				return None, None, _("Item with Item Code {0} not found").format(row[indexes["sku"]])

		return item_code, retail_sku, ""

	@frappe.whitelist()
	def get_preview_from_template(doc):
		"""
		Return the first 10 rows of the uploaded excel as preview with column headers.
		"""
		doc = frappe.get_doc("Reorder Qty From Excel", doc.name)

		if not doc.excel_file:
			return

		file_content = doc.check_file()
		if not file_content:
			return

		header = file_content[0]
		data = file_content[1:11]  # first 10 rows only

		preview_rows = []
		for row in data:
			if any(row):
				preview_rows.append(row)

		return {
			"columns": header,
			"data": preview_rows
		}

	def get_columns(self, columns):
		headers = columns.keys()
		doctype = columns["doctype"]
		doc = frappe.get_meta(columns["doctype"])
		columns = []

		for i, header in enumerate(headers):
			column = doc.get_field(header)
			if not column:
				continue
			
			if column.fieldtype != "Table":
				columns.append({
					"index": i,
					"column_number": i+1,
					"doctype": doctype,
					"header_title": column.label,
					"df": column.as_dict(),
					"is_child_table_field": None,
					"child_table_df": None,
					"skip_import": False,
				})
			else:
				child_table_df = frappe.get_meta(column.options)
				child_table_fields = child_table_df.fields

				for j, child_table_field in enumerate(child_table_fields):
					columns.append({
						"index": i,
						"column_number": i+1,
						"doctype": doctype,
						"header_title": child_table_field.label + " - " + (column.label),
						"df": column.as_dict(),
						"is_child_table_field": True,
						"child_table_df": child_table_field.as_dict(),
						"skip_import": False,
					})
		
		return columns

	def delete_or_disable_rule(self, rules):
		for rule in rules:
			try:
				frappe.delete_doc("Pricing Rule", rule.name)
			except Exception:
				frappe.clear_last_message()
				frappe.db.set_value("Pricing Rule", rule.name, "disable", 1)

		frappe.db.commit()

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
			check_in_groups = []
			request_for = []
			reorder_levels = []
			reorder_qtys = []
			material_request_types = []
			delete_rows = []

			if item.months_to_reorder:
				for month in item.months_to_reorder:
					months_to_block_reorder.append(month.month)
			if item.reorder_levels:
				for reorder_level in item.reorder_levels:
					check_in_groups.append(str(reorder_level.warehouse_group))
					request_for.append(str(reorder_level.warehouse))
					reorder_levels.append(str(reorder_level.warehouse_reorder_level))
					reorder_qtys.append(str(reorder_level.warehouse_reorder_qty))
					material_request_types.append(str(reorder_level.material_request_type))
					delete_rows.append("False")

			row = [
				item_identifier, 
	   			item.item_name, 
		  		','.join(months_to_block_reorder), 
				','.join(check_in_groups), 
			 	','.join(request_for),
			  	','.join(reorder_levels),
			   	','.join(reorder_qtys),
			   	','.join(material_request_types),
			   	','.join(delete_rows)
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
 