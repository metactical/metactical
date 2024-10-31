# Copyright (c) 2024, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
import os
from frappe import _
from frappe.utils.xlsxutils import read_xlsx_file_from_attached_file, read_xls_file_from_attached_file
from metactical.custom_scripts.utils.metactical_utils import queue_action
from frappe.utils.xlsxutils import make_xlsx
from metactical.metactical.report.pricing_rule_report___v1.pricing_rule_report___v1 import execute

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

	def create_pricing_rules(self, data):
		# Raise error if data is empty
		if not data:
			frappe.throw("No data found in the file")

		# Get header information and price list, determine column indexes
		header = data[0]
		price_list = header[3]
		indexes = self.get_column_indexes(header)

		try:
			existing_rules = []
			for row in data[1:]:
				# Prepare pricing rule data and get retail SKU
				pricing_rule_dict, retail_sku = self.get_pricing_rule(row, indexes, price_list)
				pricing_rule = frappe.get_doc(pricing_rule_dict)

				# Check for existing rules with the same price list, SKU, and priority
				rules = frappe.db.get_list("Pricing Rule", 
													filters={
														"for_price_list": price_list,
														"ifw_retailskusuffix": retail_sku,
														"priority": pricing_rule_dict["priority"]
													}, 
													fields="name"
												)
				if rules:
					existing_rules  += rules

				# Insert new pricing rule
				pricing_rule.insert()

			# Disable or delete conflicting existing rules
			if existing_rules:
				frappe.enqueue(self.delete_or_disable_rule, rules=existing_rules, job_name="delete_or_disable_pricing_rules", timeout=2000, queue="default")
		
			# Update status and comment
			frappe.db.set_value("Pricing Rule From Excel", self.name, "ais_queueu_comment", "Pricing rules created successfully", update_modified=False)

			# Commit changes
			frappe.db.commit()

			frappe.msgprint("Pricing Rules created successfully. Existing rules with the same priority will be disabled or deleted in the background.")
		# Roll back on error and log traceback
		except Exception:
			frappe.db.rollback()
			frappe.db.set_value("Pricing Rule From Excel", self.name, "ais_queueu_comment", frappe.get_traceback(), update_modified=False)

	def check_mandatory(self, data):
		header = data[0]
		indexes = self.get_column_indexes(header).values()

		for i, data in enumerate(data[1:]):
			# continue if all the columns in the row are empty
			if not any(data):
				continue
			
			for index in indexes:
				if data[index] == "" or data[index] == None:
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

		return data, retail_sku
		
	@frappe.whitelist()
	def get_preview_from_template(doc):
		doc = frappe.get_doc("Pricing Rule From Excel", doc.name)

		if not doc.excel_file:
			return

		# get the first 10 rows from the file and the columns definition
		file_content = doc.check_file()
		if not file_content:
			return

		header = file_content[0]
		data = file_content[1:11]
		price_list = header[3]
		indexes = doc.get_column_indexes(header)

		pricing_rules_list = []
		columns = []
		for i, row in enumerate(data):
			pricing_rule, retail_sku = doc.get_pricing_rule(row, indexes, price_list)
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

	def delete_or_disable_rule(self, rules):
		for rule in rules:
			try:
				frappe.delete_doc("Pricing Rule", rule.name)
			except Exception:
				frappe.clear_last_message()
				frappe.db.set_value("Pricing Rule", rule.name, "disable", 1)

		frappe.db.commit()

@frappe.whitelist()
def download_template(price_list, export_type, import_based_on="Retail SKU"):
	# Define column headers for the Excel file
	columns_list = [
		[
			"Title", import_based_on, "Item Name", price_list, "Rate or Percentage",
			f"{price_list} Discount Percentage", f"{price_list} - AfterDiscount",
			"Enabled", "Valid FromDate", "ValidToDate", "Priority"
		]
	]
	data_list = []

	# Fetch data based on export type
	if export_type != "Blank":
		params = frappe._dict({"price_list": price_list, "apply_on": "Item Code"})
		if export_type == "Five":
			params["limit"] = 5
		columns, data = execute(params)

		# Build data rows
		for d in data:
			item_identifier = d.get("item_code") if import_based_on == "ERP SKU" else d.get("retail_sku")	
			discount = d.get('discount_percentage') if d.get('rate_or_discount') == 'Discount Percentage' else d.get('rate')			
			row = [
				d.get("title"), item_identifier, d.get("item_name"), d.get("price_list_rate"), d.get("rate_or_discount"),
				discount, d.get("after_discount"), d.get("enabled"),
				d.get("valid_from"), d.get("valid_upto"), d.get("priority")
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
		"filename": "Pricing Rule Template.xlsx"
	})