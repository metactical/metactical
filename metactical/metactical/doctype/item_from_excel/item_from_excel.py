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
from frappe import _, msgprint
from frappe.model.docstatus import DocStatus
# from erpnext.controllers.item_variant import (
# 	make_variant_item_code
# )

class ItemFromExcel(Document):
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
		self.attributes = ""
		self.attribute_values = ""
  
		# collect all the last variants of the template and trigger AI update after the price list is created
		template_with_last_variant = {}
		variant_of_header = data[0].index("Variant Of") if "Variant Of" in data[0] else -1
  
		for d in data[1:] if not is_template else []:
			if d and d[0]:
				template_with_last_variant[d[variant_of_header]] = d[0]
    
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
					if field == "Attribute (Variant Attributes)" and row[i]:
						self.attributes = row[i]
					elif field == "Attribute Value (Variant Attributes)" and row[i]:
						self.attribute_values = row[i]
					else:
						if field and field.endswith(f"({parent_label})") and row[i] is not None:
							child_table = get_key_from_value(linked_dcts, doctype)
							child_table_field = updated_linked_doctypes_to_map[doctype][field]
							temp_child_table_values[child_table][child_table_field] = row[i]
       
			# check if the number of attributes and attribute values match
			if self.attributes and self.attribute_values and not is_template:
				attributes = self.attributes.split(', ') if "," in self.attributes else [self.attributes]
				attribute_values = self.attribute_values.split(', ') if not type(self.attribute_values) == int else [self.attribute_values]

				if len(attributes) != len(attribute_values):
					frappe.throw(f"Number of attributes and attribute values do not match for row {data.index(row) + 1}")
		  
		# Extract field names and price list headers from the first row
		fields = data[0]
		price_list_index = fields.index("Price List") if "Price List" in fields else -1
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
				is_last_item_of_template = True if item.variant_of and template_with_last_variant.get(item.variant_of) == item.item_code else False
				self.save_item(item, 
                   				child_table_values, 
                   				is_template, price_list_rows, 
                       			self.attributes, 
                          		self.attribute_values, 
                            	data[index][price_list_index], 
                             	is_last_item_of_template)
    
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

			# add cost to valuation rate
			if cost_column_index != -1:
				item.valuation_rate = row[cost_column_index]
    
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

		if item:
			is_last_item_of_template = True if item.variant_of and template_with_last_variant.get(item.variant_of) == item.item_code else False
			
			# Save the last item after the loop
			self.save_item(item, 
                  			child_table_values, 
                  			is_template, 
                     		price_list_rows, 
                       		self.attributes, 
                         	self.attribute_values, 
                          	data[-1][price_list_index],
							is_last_item_of_template)

	def save_item(self, item, child_table_values, is_template, price_list_rows, attributes, attribute_values, price_list, is_last_item_of_template):
     
		child_table_values = remove_duplicate_child_table_values(child_table_values)
		item = add_child_table_values_to_item(item, child_table_values, is_template, attributes, attribute_values)

		# generate the item code if it is a variant
		# if not (item.item_code and is_template):
		# 	template_item_name = frappe.db.get_value("Item", item.variant_of, "item_name")
		# 	make_variant_item_code(item.variant_of, template_item_name, item)

		# check if the template item already exists. if it does, skip creating the template item
		if is_template and frappe.db.exists("Item", item.item_code):
			return

		# set the retail sku suffix from the item code
		# item.ifw_retailskusuffix = item.item_code
  
		frappe.flags.in_import = True
		item.insert()
		supplier = item.supplier_items[0].supplier if item.supplier_items else None
		if supplier:
			self.create_item_defaults(item, supplier)
		
		# add the item_code, retail sku, and supplier to the price list rows
		price_list_rows = self.add_item_details_to_price_list(price_list_rows, item, price_list)
		
		if not is_template:
			self.create_item_price(price_list_rows)
   
		# trigger AI update for the last variant of the template
		if is_last_item_of_template:
			template_item = frappe.get_doc("Item", item.variant_of)
			template_item.request_ai_suggestion = 1
			template_item.flags.in_import = False
			template_item.flags.ignore_mandatory = True
			template_item.save()
   
	def create_item_defaults(self, item, supplier):
		frappe.get_doc({
			"doctype": "Item Default",
			"parent": item.name,
			"parenttype": "Item",
			"parentfield": "item_defaults",
			"default_supplier": supplier,
			"company": frappe.db.get_default("company")
		}).insert()

	def add_item_details_to_price_list(self, price_list_rows, item, price_list):
  
		for i, plr in enumerate(price_list_rows[1:]):
			plr.insert(0, price_list)
			if item.supplier_items:
				plr.insert(0, item.supplier_items[0].supplier)
			else:
				plr.insert(0, "")

			plr.insert(0, item.ifw_retailskusuffix)
			plr.insert(0, item.item_code)
			plr.insert(0, item.item_code)
		
		return price_list_rows

	def get_price_list_headers(self, headers, is_template):
		price_list_headers = ["Item Code", "ERPSKU", "Retail Sku", "Supplier", "Price List"]
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
  
		data, headers = self.update_data_with_supplier_price_lists(data, headers)
		for i, header in enumerate(headers):
			if header not in ["Item Code", "Item Name", "Item Group", "TemplateSKU", "ERPSKU", "Supplier", "Price List"]:
				price_list = frappe.db.exists("Price List", {"name": header})

				if price_list:
					price_lists.append(header)
					price_list_headers_index.append(i)

		# get all the default price lists for the suppliers

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

	# get supplier's price list and append it at the end of the headers and update the data with the cost
	def update_data_with_supplier_price_lists(self, data, headers):
		headers = headers.copy()
		price_list_index = headers.index("Price List")
		cost_column_index = headers.index("Cost")
  
		# get all the suppliers from the excel (Price List sheet)
		price_lists = [row[price_list_index] for row in data[1:] if row[price_list_index] is not None]
		price_lists = list(set(price_lists))
		
		# if there are suppliers with price lists, update the data with the price list and the cost
		if len(price_lists) > 0:
			for i, d in enumerate(data):
				# add empty values to all the rows to match the price list columns because the suppier price lists are added in the header
				if price_lists and i != 0:
					d += [None] * len(price_lists)

				if i == 0:
					for pl in price_lists:
						if pl not in headers:
							headers.append(pl)

				else:
					cost = d[cost_column_index]
					index = headers.index(d[price_list_index])
					d[index] = cost

			data[0] = headers
   
		return data, headers

	def on_submit(self):
		file_content = self.check_file()
		linked_doctypes, item_field_map, required_fields = get_doctype_information()

		try:
			self.create_item(file_content[0], item_field_map, linked_doctypes, True)
			self.create_item(file_content[1], item_field_map, linked_doctypes, False)
		
			frappe.db.commit()
		except Exception as e:
			frappe.db.rollback()
			frappe.clear_last_message()
			frappe.log_error(title="Error creating items", message=frappe.get_traceback())
			frappe.throw(f"Error creating items: {e}")
			self.db_set("ais_queueu_comment", e)

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

def add_child_table_values_to_item(item, child_table_values, is_template, attributes, attribute_values):
	from frappe.client import validate_link
	child_table_values['attributes'] = []
 	
	add_attributes_to_child_table(item, child_table_values, attributes, attribute_values, is_template)
	
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

def add_attributes_to_child_table(item, child_table_values, attributes, attribute_values, is_template=False):
	attr_list = attributes.split(', ') if "," in attributes else [attributes]
	attr_values_list = attribute_values.split(', ') if not type(attribute_values) == int else [attribute_values]

	if is_template:
		for attr in attr_list:
			is_numeric = frappe.db.get_value("Item Attribute", {"name": attr.strip()}, "numeric_values")
			child_table_values['attributes'].append({
				"attribute": attr.strip(),
				"attribute_value": None,
				"numeric_values": is_numeric
			})
	else:
		for i, attr in enumerate(attr_list):
			is_numeric = frappe.db.get_value("Item Attribute", {"name": attr.strip()}, "numeric_values")
			child_table_values['attributes'].append({
				"variant_of": item.variant_of,
				"attribute": attr.strip(),
				"attribute_value": attr_values_list[i].strip() if type(attr_values_list[i]) == str else attr_values_list[i],
				"numeric_values": is_numeric
			})

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