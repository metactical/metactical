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
from erpnext.controllers.item_variant import (
	make_variant_item_code
)

class ItemFromExcel(Document):
	def validate(self):
		file_content = self.check_file()
		item_doctype_meta = frappe.get_meta("Item")

		linked_doctypes, item_field_map, required_fields = get_doctype_information()

		# check if all required fields are present
		if len(file_content) < 2:
			frappe.throw(f"Required number of sheets not found in the uploaded file. Expected 2 (Template, Variant), found {len(file_content)}")

		for field in required_fields:
			if field not in file_content[0][0]:
				frappe.throw(f"Required field {field} not found in the uploaded file")

			if field not in file_content[1][0]:
				frappe.throw(f"Required field {field} not found in the uploaded file")
		
		self.check_mandatory_fields(file_content[0], required_fields, is_template=True)
		self.check_mandatory_fields(file_content[1], required_fields, is_template=False)

	def check_mandatory_fields(self, data, mandatory_fields, is_template):
		headers = data[0]
		mandatory_fields_index = [i for i, x in enumerate(headers) if x in mandatory_fields]

		for d in data[1:]:
			for i in mandatory_fields_index:
				if not d[i] and d[0]:
					frappe.throw(f"Value missing for field {headers[i]} at row {data.index(d) + 1}")

	def create_item(self, data, item_field_map, linked_dcts, is_template):
		# Helper function to initialize data structures for a new item
		def initialize_item_data():
			return frappe.new_doc("Item"), "", {ld: [] for ld in linked_dcts}, {ld: {} for ld in linked_dcts}, [price_list_headers]

		# Helper function to update the item's fields based on the provided field and value
		def update_item_field(item, field, value):
			if field in item_field_map and value is not None:
				item.set(item_field_map[field], value)

		# Helper function to process linked doctypes and update temporary child table values
		def process_linked_doctypes(fields, row):
			for doctype in updated_linked_doctypes_to_map:
				parent_label = get_parent_label(linked_dcts, doctype)

				for i, field in enumerate(fields):
					if field and field.endswith(f"({parent_label})") and row[i] is not None:
						child_table = get_key_from_value(linked_dcts, doctype)
						child_table_field = updated_linked_doctypes_to_map[doctype][field]
						temp_child_table_values[child_table][child_table_field] = row[i]

		# Extract field names and price list headers from the first row
		fields = data[0]
		price_list_headers, cost_column_index, item_name_column = self.get_price_list_headers(fields, is_template)
		linked_doctypes_to_map, updated_linked_doctypes_to_map = get_linked_doctypes(linked_dcts, fields)

		# Initialize item and related data structures
		item, item_code, child_table_values, temp_child_table_values, price_list_rows = initialize_item_data()

		# Iterate over each row in the data (excluding the first row)
		for index, row in enumerate(data[1:]):
			# Determine the row to check depending on whether the item name or item code
			row_to_check = row[0] if is_template else row[item_name_column]

			# If starting a new item, save the current one and reinitialize variables
			if index > 0 and row_to_check and item_code != row_to_check:
				self.save_item(item, child_table_values, is_template, price_list_rows)
				item, item_code, child_table_values, temp_child_table_values, price_list_rows = initialize_item_data()

			prices = []

			# Iterate over each field in the current row
			for i, field in enumerate(fields):
				# Process item fields before the cost column index
				if i < cost_column_index or cost_column_index == -1:
					if index == 0:
						item_code = row_to_check
					update_item_field(item, field, row[i])
				# Process price fields for non-template items
				elif not is_template and i >= cost_column_index:
					prices.append(row[i])

			# Append prices to the price list if there are any valid prices
			if prices and not all(p is None for p in prices):
				price_list_rows.append(prices)
			
			# Process linked doctypes and update child table values
			process_linked_doctypes(fields, row)
			
			# Transfer temporary child table values to the main child table values
			for child_table, temp_values in temp_child_table_values.items():
				if temp_values:
					child_table_values[child_table].append(temp_values.copy())
					temp_child_table_values[child_table] = {}

		# Save the last item after the loop
		if item:
			self.save_item(item, child_table_values, is_template, price_list_rows)

	def save_item(self, item, child_table_values, is_template, price_list_rows):
		child_table_values = remove_duplicate_child_table_values(child_table_values)
		item = add_child_table_values_to_item(item, child_table_values, is_template)

		# generate the item code if it is a variant
		if not (item.item_code and is_template):
			template_item_name = frappe.db.get_value("Item", item.variant_of, "item_name")
			make_variant_item_code(item.variant_of, template_item_name, item)

		# check if the template item already exists. if it does, skip creating the template item
		elif is_template and frappe.db.exists("Item", item.item_code):
			return

		# set the retail sku suffix from the item code
		item.ifw_retailskusuffix = item.item_code
		item.insert()
		
		# add the item_code, retail sku, and supplier to the price list rows
		price_list_rows = self.add_item_details_to_price_list(price_list_rows, item)
		
		if not is_template:
			self.create_item_price(price_list_rows)

	def add_item_details_to_price_list(self, price_list_rows, item):
		for plr in price_list_rows[1:]:
			if item.supplier_items:
				plr.insert(0, item.supplier_items[0].supplier)
			else:
				plr.insert(0, "")

			plr.insert(0, item.ifw_retailskusuffix)
			plr.insert(0, item.item_code)
			plr.insert(0, item.item_code)
		
		return price_list_rows

	def get_price_list_headers(self, headers, is_template):
		price_list_headers = ["Item Code", "ERPSKU", "Retail Sku", "Supplier"]
		cost_column_index = -1
		item_name_column = -1

		if not is_template:
			for i, header in enumerate(headers):
				if header == "Item Name":
					item_name_column = i
				elif header == "Cost":
					cost_column_index = i
				
				if cost_column_index != -1:
					price_list_headers.append(header)

			if cost_column_index == -1:
				frappe.throw("Cost column not found in variant sheet")

		return price_list_headers, cost_column_index, item_name_column


	def create_item_price(self, data):
		# add the items to the price list

		headers = data[0]
		price_lists = []
		price_list_headers_index = []
		suppliers_header_index = None


		for i, header in enumerate(headers):
			if header not in ["Item Code", "Item Name", "Item Group", "TemplateSKU", "ERPSKU", "Supplier"]:
				price_list = frappe.db.exists("Price List", {"name": header})

				if price_list:
					price_lists.append(header)
					price_list_headers_index.append(i)
			elif header == "Supplier":
				suppliers_header_index = i

		# get all the default price lists for the suppliers
		if suppliers_header_index:
			data = self.update_data_with_supplier_price_lists(data, suppliers_header_index, headers)

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
	
		ItemPriceFromExcel.create_price_entries(self, updated_data, True)

	def update_data_with_supplier_price_lists(self, data, suppliers_header_index, headers):
		supplier_with_price_list = {}

		# get all the suppliers from the excel (Price List sheet)
		suppliers = [row[suppliers_header_index] for row in data[1:] if row[suppliers_header_index] is not None]
		suppliers = list(set(suppliers))

		# get all the default price lists for the suppliers
		for supplier in suppliers:
			price_list = frappe.db.get_value("Supplier", {"name": supplier}, "default_price_list")
			if price_list:
				supplier_with_price_list[supplier] = price_list
		
		# if there are suppliers with price lists, update the data with the price list and the cost
		if len(supplier_with_price_list) > 0:
			supplier_costs = list(set(supplier_with_price_list.values()))

			for i, d in enumerate(data):
				# add empty values to all the rows to match the price list columns because the suppier price lists are added in the header
				if supplier_costs and i != 0:
					d += [None] * len(supplier_costs)

				if i == 0:
					for sc in supplier_costs:
						if sc not in headers:
							headers.append(sc)

				else:
					cost = d[suppliers_header_index+1]
					supplier = d[suppliers_header_index]
					price_list = supplier_with_price_list[supplier]
					suplier_price_list_index = headers.index(price_list)
					d[suplier_price_list_index] = cost

		return data

	def on_submit(self):
		file_content = self.check_file()
		linked_doctypes, item_field_map, required_fields = get_doctype_information()

		try:
			self.create_item(file_content[0], item_field_map, linked_doctypes, True)
			self.create_item(file_content[1], item_field_map, linked_doctypes, False)
		
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

def add_child_table_values_to_item(item, child_table_values, is_template):
	from frappe.client import validate_link

	for child in child_table_values:
		if child == "attributes" and is_template:
			for attr in child_table_values[child]:
				is_numeric = frappe.db.get_value("Item Attribute", {"name": attr["attribute"]}, "numeric_values")
				if is_numeric:
					props = frappe.db.get_value("Item Attribute", {"name": attr["attribute"]}, ["from_range", "to_range", "increment"], as_dict=1)
					attr["from_range"] = props["from_range"]
					attr["to_range"] = props["to_range"]
					attr["increment"] = props["increment"]
					attr["numeric_values"] = 1

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