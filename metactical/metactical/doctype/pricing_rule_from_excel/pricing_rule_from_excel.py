# Copyright (c) 2024, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
import os
import datetime
from frappe import _
from frappe.utils.xlsxutils import read_xlsx_file_from_attached_file, read_xls_file_from_attached_file
from metactical.custom_scripts.utils.metactical_utils import queue_action
from frappe.utils.xlsxutils import make_xlsx
from metactical.metactical.report.pricing_rule_report___v1.pricing_rule_report___v1 import execute
from frappe import _, msgprint
from frappe.model.docstatus import DocStatus

class PricingRuleFromExcel(Document):
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
		headers = ["Valid FromDate", "ValidToDate", "Enabled", "Rate or Discount Percentage"]
		for header in headers:
			if header not in file_content[0]:
				frappe.throw(f"Column <b>{header}</b> is missing")
		self.check_mandatory(file_content)

	def on_submit(self):
		file_content = self.check_file()
		self.check_mandatory(file_content)
		self.create_pricing_rules(file_content)

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
		error_messages = ""
		new_rules = []
		existing_rules = []

		try:
			for row in data[1:]:
				# Prepare pricing rule data and get retail SKU
				pricing_rule_dict, retail_sku, message = self.get_pricing_rule(row, indexes, price_list)
				if not retail_sku:
					error_messages += message + "\n"
					continue

				# Check for existing rules with the same price list, SKU, and priority
				rules = frappe.db.get_list("Pricing Rule", 
													filters={"title": pricing_rule_dict["title"]}, 
													fields="name"
												)

				if rules:
					# update pricing rule information
					for rule in rules:
						pricing_rule = frappe.get_doc("Pricing Rule", rule.name)
						pricing_rule.update(pricing_rule_dict)
						pricing_rule.flags.ignore_validate = True
						existing_rules.append(pricing_rule)
				else:
					pricing_rule_dict["naming_series"] = self.pr_naming_series
					pricing_rule = frappe.get_doc(pricing_rule_dict)

					# Insert new pricing rule
					pricing_rule.flags.ignore_validate = True
					new_rules.append(pricing_rule)

				if existing_rules and len(existing_rules) % 1000 == 0:
					frappe.enqueue(update_existing_prs, existing_rules=existing_rules, queue="long", job_name="update_existing_prs")
					existing_rules = []

				if new_rules and len(new_rules) % 1000 == 0:
					frappe.enqueue(create_new_prs, prs_list=new_rules, queue="long", job_name="create_new_prs")
					new_rules = []

			# Create new pricing rules
			if new_rules:
				frappe.enqueue(create_new_prs, prs_list=new_rules, queue="long", job_name="create_new_prs")

			# Update existing pricing rules
			if existing_rules:
				frappe.enqueue(update_existing_prs, existing_rules=existing_rules, queue="long", job_name="update_existing_prs")

			# Log error messages
			if error_messages:
				frappe.log_error(title=f"pricing rule import error - {self.name}", message=error_messages)
				frappe.msgprint("Some rows failed to import. Please refer to the error log for more information.")
		
		# Roll back on error and log traceback
		except Exception:
			frappe.db.rollback()
			frappe.throw(frappe.get_traceback())

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
			elif col == "Rate or Discount Percentage":
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
			
		# if not item_code and item_code is not None:
		# 	frappe.throw(f"Item with Retail SKU Suffix <b>{row[1]}</b> not found")
		# elif item_code is None:
		# 	frappe.throw(f"Item with Retail SKU Suffix <b>{row[1]}</b> not found")
		if not item_code:
			if self.import_based_on == "Retail SKU":
				message=f"Item with Retail SKU Suffix *{retail_sku}* not found"
			else:
				message=f"Item with Item Code *{item_code}* not found"
			return None, None, message

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

		return data, retail_sku, ""
		
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
		messages = ""
		for i, row in enumerate(data):
			pricing_rule, retail_sku, message = doc.get_pricing_rule(row, indexes, price_list)
			if not retail_sku:
				messages += message + "\n"
				continue

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
			"Title", import_based_on, "Item Name", price_list, "Rate or Discount Percentage",
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
			if d.get("valid_from"):
				
				d["valid_from"] = change_date_format2(d.get("valid_from"))
			if d.get("valid_upto"):
				d["valid_upto"] = change_date_format2(d.get("valid_upto"))

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

# convert date format from 2014-08-31 to 31-Aug-14 
def change_date_format2(date):
	if (type(date) == datetime.date):
		date = date.strftime("%Y-%m-%d")
	elif not date:
		return ""

	months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
	date = date.split("-")
	return f"{date[2]}-{months[int(date[1])-1]}-{date[0][2:]}"


def create_new_prs(prs_list):
	for pr in prs_list:
		pr.insert()
	frappe.db.commit()

def update_existing_prs(existing_rules):
	for rule in existing_rules:
		rule.save()
	frappe.db.commit()
