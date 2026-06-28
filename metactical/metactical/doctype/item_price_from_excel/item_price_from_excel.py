# Copyright (c) 2024, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
import os
from frappe.utils.xlsxutils import read_xlsx_file_from_attached_file, read_xls_file_from_attached_file
from metactical.custom_scripts.utils.metactical_utils import queue_action
from frappe import _, msgprint
from frappe.model.docstatus import DocStatus

class ItemPriceFromExcel(Document):
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

	def on_submit(self):
		file_content = self.check_file()
		data_rows = file_content[1:]
		if len(data_rows) > 3000:
			header = file_content[0]
			for start in range(0, len(data_rows), 3000):
				batch = data_rows[start:start + 3000]
				frappe.enqueue(
					"metactical.metactical.doctype.item_price_from_excel.item_price_from_excel.process_batch",
					queue="long",
					timeout=3600,
					doc_name=self.name,
					header=header,
					batch=batch,
					import_based_on=self.import_based_on,
					replace_existing=self.replace_existing,
				)
			msgprint(_("File has more than 3000 rows. Processing in background batches."))
		else:
			self.create_price_entries(file_content)

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
	
	def read_file(self):
		file_path = self.excel_file
		extn = os.path.splitext(file_path)[1][1:]

		file_content = None

		file_name = frappe.db.get_value("File", {"file_url": file_path})
		if file_name:
			file = frappe.get_doc("File", file_name)
			file_content = file.get_content()

		return file_content, extn

	def create_price_entries(self, data, external_source=False):
		item_code_col = None
		item_sku_col = None
		price_lists = []

		for col in data[0]:
			if col in ["ItemCode", "ERPSKU"]:
				item_code_col = data[0].index(col)
			elif col in ["Retail SKU"]:
				item_sku_col = data[0].index(col)
			else:
				# Check if it's a price list
				price_list = frappe.db.exists("Price List", {"name": col})
				if price_list:
					price_lists.append(col)
					
		if price_lists == []:
			frappe.throw("No price list found in the file")

		# Pre-build lookup maps for Retail SKU import to avoid per-row DB queries
		sku_to_item = {}
		sku_to_existing_price = {}  # (sku, price_list) -> item_price_name
		if self.import_based_on == "Retail SKU" and item_sku_col is not None:
			all_skus = list({row[item_sku_col] for row in data[1:] if row[item_sku_col]})
			if all_skus:
				item_rows = frappe.db.sql(
					"SELECT name, ifw_retailskusuffix FROM `tabItem` WHERE ifw_retailskusuffix IN %(skus)s",
					{"skus": all_skus}, as_dict=1
				)
				sku_to_item = {r.ifw_retailskusuffix: r.name for r in item_rows}

				missing_skus = [sku for sku in all_skus if sku not in sku_to_item]
				if missing_skus:
					frappe.msgprint(
						_("The following Retail SKUs were not found in the system and will be skipped:<br><br>{0}").format(
							"<br>".join(str(s) for s in missing_skus)
						),
						title=_("Missing Retail SKUs"),
						indicator="red",
					)

				if sku_to_item and price_lists:
					ip_rows = frappe.db.sql(
						"""SELECT item_price.name, item.ifw_retailskusuffix, item_price.price_list
						   FROM `tabItem Price` item_price
						   LEFT JOIN `tabItem` AS item ON item.name = item_price.item_code
						   WHERE item.ifw_retailskusuffix IN %(skus)s AND item_price.price_list IN %(lists)s""",
						{"skus": all_skus, "lists": price_lists}, as_dict=1
					)
					sku_to_existing_price = {(r.ifw_retailskusuffix, r.price_list): r.name for r in ip_rows}

		count = 0
		for row in data[1:]:
			item_code = None
			item_sku = None

			if item_code_col is not None:
				item_code = row[item_code_col]

			if item_sku_col is not None:
				item_sku = row[item_sku_col]
			
			for price_list in price_lists:
				price = row[data[0].index(price_list)]
				if item_code is not None and item_code != "" and self.import_based_on == "ERP SKU":
					exists = frappe.db.exists("Item Price", {"item_code": item_code, "price_list": price_list})
				elif item_sku is not None and item_sku != "" and self.import_based_on == "Retail SKU":
					item_code = sku_to_item.get(item_sku)
					exists = sku_to_existing_price.get((item_sku, price_list), False)

				if not self.replace_existing and exists:
					continue
				elif item_code is None or item_code == "":
					continue
				else:
					if exists:
						doc = frappe.get_doc("Item Price", exists)
					else:
						doc = frappe.new_doc("Item Price")

					if not price and external_source:
						continue

					doc.update({
						"item_code": item_code,
						"price_list": price_list,
						"price_list_rate": price,
					})
					try:
						if price:
							doc.save()
							# Update cache so subsequent rows see newly created record
							if item_sku and not exists:
								sku_to_existing_price[(item_sku, price_list)] = doc.name
							count += 1
							if count % 100 == 0:
								frappe.db.commit()
					except Exception as e:
						frappe.clear_last_message()
						frappe.throw(str(e))
						# frappe.log_error(frappe.get_traceback())
						# error_log = frappe.new_doc("Item Price From Excel Error")
						# error_log.update({
						# 	"error": e,
						# 	"item_code": item_code,
						# 	"rate": price,
						# 	"parenttype": self.doctype,
						# 	"parent": self.name,
						# 	"parentfield": "error_log"
						# })
						# error_log.insert()

		frappe.db.commit()


def process_batch(doc_name, header, batch, import_based_on, replace_existing):
	"""Background job entrypoint for a single batch of rows (>3000 row files)."""
	try:
		doc = frappe.get_doc("Item Price From Excel", doc_name)
		doc.import_based_on = import_based_on
		doc.replace_existing = replace_existing
		doc.create_price_entries([header] + batch)
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"ItemPriceFromExcel batch error: {doc_name}")