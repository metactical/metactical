# Copyright (c) 2024, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
import os
from frappe.utils.xlsxutils import read_xlsx_file_from_attached_file, read_xls_file_from_attached_file
from metactical.custom_scripts.utils.metactical_utils import queue_action

class PricingRuleFromExcel(Document):
	def submit(self):
		frappe.msgprint(
			"""The task has been enqueued as a background job. In case there is any issue on processing in background, 
			the system will add a comment about the error on this document and revert to the Draft stage"""
		)
		queue_action(self, "submit", timeout=2000)

	def on_submit(self):
		file_content = self.check_file()
		self.check_mandatory(file_content)
		self.create_pricing_rules(file_content)

	
	def validate(self):
		file_content = self.check_file()
		headers = ["Valid FromDate", "ValidToDate", "Enabled", "Rate or Percentage"]
		for header in headers:
			if header not in file_content[0]:
				frappe.throw(f"Column <b>{header}</b> is missing")
		self.check_mandatory(file_content)

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

	def create_pricing_rules(self, data):
		if not data:
			frappe.throw("No data found in the file")

		header = data[0]
		price_list = header[3]
		indexes = self.get_column_indexes(header)

		for row in data[1:]:
			pricing_rule = frappe.get_doc(self.get_pricing_rule(row, indexes, price_list))

			get_same_pricing_rules = frappe.db.get_list("Pricing Rule", filters={"for_price_list": price_list, "priority": pricing_rule.priority, "ifw_retailskusuffix": retail_sku}, fields="name")
			pricing_rule.insert()

			if get_same_pricing_rules:
				for pricing_rule in get_same_pricing_rules:
					pricing_rule = frappe.get_doc("Pricing Rule", pricing_rule.name)
					pricing_rule.delete()

			frappe.db.commit()

	def check_mandatory(self, data):
		header = data[0]
		indexes = self.get_column_indexes(header).values()

		for i, data in enumerate(data[1:]):
			# continue if all the columns in the row are empty
			if not any(data):
				continue

			for index in indexes:
				if not data[index]:
					frappe.throw(f"Column <b>{header[index]}</b> is mandatory in row {i+2}")

		
	def get_last_pricing_rule(self, item_code, price_list=""):
		pricing_rules = frappe.db.sql(f"""
			SELECT title
			FROM `tabPricing Rule`
			WHERE for_price_list = '{price_list}'
			ORDER BY creation DESC
			LIMIT 5
		""", as_dict=True)

		# get the last number from the pricing rule name
		if pricing_rules:
			for pricing_rule in pricing_rules:
				pricing_rule = pricing_rule["title"].split("-")

				if len(pricing_rule) > 1:
					if pricing_rule[-1].isdigit():
						pricing_rule = int(pricing_rule[-1])
						return pricing_rule
		return None

	def get_column_indexes(self, header):
		indexes = {}
		for i, col in enumerate(header):
			if not col:
				continue

			if col == "Valid FromDate":
				indexes["valid_from"] = i
			elif col == "Title":
				indexes["title"] = i
			elif col == "Retail SKU":
				indexes["retail_sku"] = i
			elif col == "ValidToDate":
				indexes["valid_to"] = i
			elif col == "Enabled":
				indexes["enabled"] = i
			elif col == "Rate or Percentage":
				indexes["rate_or_discount"] = i
			elif col.endswith("Discount Percentage"):
				indexes["discount_percentage"] = i
			elif col == "Priority":
				indexes["priority"] = i

		return indexes

	# convert date format from 31-Aug-14 to 2014-08-31
	def change_date_format(self, date):
		if (type(date) != str):
			return date

		months = {
			"Jan": "01",
			"Feb": "02",
			"Mar": "03",
			"Apr": "04",
			"May": "05",
			"Jun": "06",
			"Jul": "07",
			"Aug": "08",
			"Sep": "09",
			"Oct": "10",
			"Nov": "11",
			"Dec": "12"
		}
		date = date.split("-")
		return f"20{date[2]}-{months[date[1]]}-{date[0]}"

	def get_pricing_rule(self, row, indexes, price_list):
		retail_sku = ""
		if self.import_based_on == "Retail SKU":
			item_code = frappe.db.get_value("Item", {"ifw_retailskusuffix": row[1]}, "name")
			retail_sku = row[1]
		else:
			item_code = row[1]
			retail_sku = frappe.db.get_value("Item", item_code, "ifw_retailskusuffix")
		
		if not item_code and item_code is not None:
			frappe.throw(f"Item with Retail SKU Suffix {row[0]} not found")
		elif item_code is None:
			return

		data = {
			"title": row[indexes["title"]],
			"doctype": "Pricing Rule",
			"for_price_list": price_list,
			"selling": 1,
			"ifw_retailskusuffix": retail_sku,
			"has_priority": 1,
			"priority": row[indexes["priority"]],
			"valid_from": self.change_date_format(row[indexes["valid_from"]]),
			"valid_upto": self.change_date_format(row[indexes["valid_to"]]),
			"rate_or_discount": "Rate" if row[indexes["rate_or_discount"]].lower() == "rate" else "Discount Percentage",
			"rate": row[indexes["discount_percentage"]] if row[indexes["rate_or_discount"]].lower() == "rate" else 0,
			"discount_percentage": row[indexes["discount_percentage"]] if row[indexes["rate_or_discount"]].lower() == "discount percentage" else 0,
			"disable": not row[indexes["enabled"]],
			"items": [
				{
					"item_code": item_code,
					"uom": "Nos",
				}
			]
		}

		return data
		
	@frappe.whitelist()
	def get_preview_from_template(doc):
		doc = frappe.get_doc("Pricing Rule From Excel", doc.name)
		
		# get the first 10 rows from the file and the columns definition
		file_content = doc.check_file()
		header = file_content[0]
		data = file_content[1:11]
		price_list = header[3]
		indexes = doc.get_column_indexes(header)

		pricing_rules_list = []
		columns = []
		for i, row in enumerate(data):
			pricing_rule = doc.get_pricing_rule(row, indexes, price_list)
			if not columns:
				columns = doc.get_columns(pricing_rule)
			
			# add all values from pricing rule except doctype

			row = []
			for field, value in pricing_rule.items():
				if field == "doctype":
					continue
				
				if type(value) != list:
					row.append(value)
				else:
					row.append(value[0]["item_code"])
					row.append(value[0]["uom"])
			
			print(row)
			pricing_rules_list.append(row)

		return {
			"columns": columns,
			"data": pricing_rules_list
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


