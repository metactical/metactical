# Copyright (c) 2024, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
import os
from frappe.model.document import Document
from frappe.utils.xlsxutils import read_xls_file_from_attached_file
from metactical.custom_scripts.utils.metactical_utils import queue_action
from openpyxl import load_workbook
from io import BytesIO
from metactical.metactical.doctype.item_price_from_excel.item_price_from_excel import ItemPriceFromExcel

class ItemFromExcel(Document):
	def validate(self):
		file_content = self.check_file()
		item_doctype_meta = frappe.get_meta("Item")

		linked_doctypes, item_field_map, required_fields = get_doctype_information()

		# check if all required fields are present
		for field in required_fields:
			if field not in file_content[0][0]:
				raise(f"Required field {field} not found in the uploaded file")

			if field not in file_content[1][0]:
				raise(f"Required field {field} not found in the uploaded file")
		
		self.check_mandatory_fields(file_content[0], required_fields)
		self.check_mandatory_fields(file_content[1], required_fields)

	def check_mandatory_fields(self, data, mandatory_fields):
		headers = data[0]
		mandatory_fields_index = [i for i, x in enumerate(headers) if x in mandatory_fields]

		for d in data[1:]:
			for i in mandatory_fields_index:
				if not d[i] and d[0]:
					frappe.throw(f"Value missing for field {headers[i]} at row {data.index(d) + 1}")

	def create_item(self, data, item_field_map, linked_dcts):
		# create item template
		fields = data[0]		
		linked_doctypes_to_map, updated_linked_doctypes_to_map = get_linked_doctypes(linked_dcts, fields)

		child_table_values = {}
		child_table_values_temp = {}
		# create item and linked doctypes
		
		for ld in linked_dcts:
			child_table_values[ld] = []
			child_table_values_temp[ld] = {}

		item_code = ""
		item = frappe.new_doc("Item")

		for index, row in enumerate(data[1:]):
			child_table_values_temp2 = child_table_values_temp.copy()

			# insert an item when the item code changes if the new row is not empty
			if index > 0 and row[0] and item_code != row[0]:
				child_table_values = remove_duplicate_child_table_values(child_table_values)
				item = add_child_table_values_to_item(item, child_table_values)

				item.insert()
				item_code = row[0]
				item = frappe.new_doc("Item")

			for i, field in enumerate(fields):
				if index == 0: 
					item_code = row[0]

				if field in item_field_map:
					if row[0] is not None: # if the field is standard field and has item code in the row
						item.set(item_field_map[field], row[i])
				else: # if the column is from a child table
					for doctype in updated_linked_doctypes_to_map:
						parent_label = get_parent_label(linked_dcts, doctype)

						if field.endswith("("+parent_label+")") and row[i] is not None:
							child_table = get_key_from_value(linked_dcts, doctype)

							child_table_field = updated_linked_doctypes_to_map[doctype][field]
							child_table_values_temp2[child_table][child_table_field] = row[i]


			for child in child_table_values_temp2:
				if len(child_table_values_temp2[child]):
					attr = child_table_values_temp2[child].copy()
					child_table_values[child].append(attr)
					child_table_values_temp2[child] = {}

		# add the last item 
		child_table_values = remove_duplicate_child_table_values(child_table_values)
		if item:
			item = add_child_table_values_to_item(item, child_table_values)
			item.insert()
	
	def create_item_price(self, data):
		headers = data[0]
		price_lists = []
		price_list_headers_index = []

		for i, header in enumerate(headers):
			if header not in ["Item Code", "Item Name", "Item Group", "TemplateSKU", "ERPSKU"]:
				price_list = frappe.db.exists("Price List", {"name": header})

				if price_list:
					price_lists.append(header)
					price_list_headers_index.append(i)
		
		# get price lists if all the cells in the column are empty
		columns_to_remove = []
		for plhi in price_list_headers_index:
			found = False
			for data_row in data[1:]:
				if data_row[plhi] is not None:
					found = True
					break

			if not found:
				columns_to_remove.append(plhi)

		if price_lists == [] or len(price_lists) == len(columns_to_remove):
			return

		# remove all the price list columns that have all empty/None cells
		updated_data = []
		for row in data:
			updated_data.append([row[i] for i in range(len(row)) if i not in columns_to_remove])
	
		ItemPriceFromExcel.create_price_entries(self, updated_data)

	def on_submit(self):
		file_content = self.check_file()
		linked_doctypes, item_field_map, required_fields = get_doctype_information()

		try:
			self.create_item(file_content[0], item_field_map, linked_doctypes)
			self.create_item(file_content[1], item_field_map, linked_doctypes)
			self.create_item_price(file_content[2])
			
			frappe.db.commit()
		except Exception as e:
			frappe.db.rollback()
			frappe.throw(f"Error creating items: {e}")
			self.db_set("ais_queueu_comment", e)

	def submit(self):
		frappe.msgprint(
			"""The task has been enqueued as a background job. In case there is any issue on processing in background, 
			the system will add a comment about the error on this document and revert to the Draft stage"""
		)
		queue_action(self, "submit", timeout=2000)

	def read_file(self):
		file_path = self.excel_file
		extn = os.path.splitext(file_path)[1][1:]

		file_content = None

		file_name = frappe.db.get_value("File", {"file_url": file_path})
		if file_name:
			file = frappe.get_doc("File", file_name)
			file_content = file.get_content()

		return file_content, extn

	def check_file(self):
		file_content, extn = self.read_file()
		if extn == "xlsx":
			file_content = self.read_xlsx_file_from_attached_file(fcontent=file_content)
		elif extn == "xls":
			file_content = read_xls_file_from_attached_file(file_content)
		else:
			frappe.throw("Only xls and xlsx files are supported.")
		
		# Cleaned data
		cleaned_data = remove_all_none_rows(file_content)
		return cleaned_data

	def read_xlsx_file_from_attached_file(self, fcontent=None):
		if fcontent:
			filename = BytesIO(fcontent)
		elif filepath:
			filename = filepath
		else:
			return

		sheets = []
		wb1 = load_workbook(filename=filename, read_only=True, data_only=True)
		for ws in wb1.worksheets:
			rows = []
			for row in ws.iter_rows():
				tmp_list = []
				for cell in row:
					tmp_list.append(cell.value)
				rows.append(tmp_list)
			sheets.append(rows)

		return sheets

def get_linked_doctypes(linked_dcts, fields):
	linked_doctypes_to_map = []

	# get all the fields that are used in the excel
	for field, prop in linked_dcts.items():
		for field in fields:
			if field:
				if field.endswith("("+prop['label']+")"):
					linked_doctypes_to_map.append(prop['doctype'])

	linked_doctypes_to_map = list(set(linked_doctypes_to_map))
	linked_doctypes_map = get_linked_doctypes_map(linked_doctypes_to_map)

	# prepare linked doctype fields to match the columns in the excel
	# eg. instead of Attribute (Item Variant Attribute) it should be Attribute (Attributes)
	updated_linked_doctypes_to_map = {}
	for doctype in linked_doctypes_to_map:
		for field in linked_doctypes_map[doctype]:
			if field:
				if not doctype in updated_linked_doctypes_to_map:
					updated_linked_doctypes_to_map[doctype] = {}

				parent_label = get_parent_label(linked_dcts, doctype)
				
				if not field["label"]:
					continue

				label = field["label"] + " ("+parent_label+")"
				updated_linked_doctypes_to_map[doctype][label] = field["fieldname"]

	return linked_doctypes_to_map, updated_linked_doctypes_to_map

def add_child_table_values_to_item(item, child_table_values):
	for child in child_table_values:
		if len(child_table_values[child]):
			item.set(child, child_table_values[child])
			child_table_values[child] = []

	return item

def get_doctype_information():
	item_doctype_meta = frappe.get_meta("Item")
	item_field_map = {}
	linked_doctypes = {}
	required_fields = []

	# create matching dict for item doctype {label: fieldname} 
	for field in item_doctype_meta.fields:
		item_field_map[field.label] = field.fieldname

		if field.fieldtype == "Table":
			linked_doctypes[field.fieldname] = {
				"doctype": field.options,
				"label": field.label
			}

			if field.reqd:
				required_fields.append(field.label)

	return linked_doctypes, item_field_map, required_fields

def get_key_from_value(d, value):
	for key, val in d.items():
		if val["doctype"] == value:
			return key
	return None

def get_linked_doctypes_map(linked_doctypes):
	linked_doctypes_map = {}
	for doctype in linked_doctypes:
		meta = frappe.get_meta(doctype)
		field_map = {}
		for field in meta.fields:
			field_map["fieldname"] = field.fieldname
			field_map["label"] = field.label

			if doctype not in linked_doctypes_map:
				linked_doctypes_map[doctype] = []

			linked_doctypes_map[doctype].append(field_map)
			field_map = {}

	return linked_doctypes_map

def get_parent_label(linked_doctypes, doctype):
	for d in linked_doctypes:
		if linked_doctypes[d]["doctype"] == doctype:
			return linked_doctypes[d]["label"]
	return None

# Function to remove rows with all None values
def remove_all_none_rows(data):
    return [[row for row in table if not all(value is None for value in row)] for table in data]

def remove_duplicate_child_table_values(data):
	return {key: [dict(t) for t in {tuple(d.items()) for d in data[key]}] for key in data}