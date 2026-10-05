# Copyright (c) 2025, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _, msgprint
from frappe.model.document import Document
from frappe.utils.xlsxutils import read_xlsx_file_from_attached_file, read_xls_file_from_attached_file
from frappe.model.docstatus import DocStatus
from frappe.utils.file_manager import save_file
from metactical.custom_scripts.utils.metactical_utils import queue_action
import os


class ItemSupplierImportTool(Document):
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

	def on_submit(self):
		file_content = self.check_file()
		self.edit_item_supplier(file_content)

	def read_file(self):
		file_path = self.excel_file
		extn = os.path.splitext(file_path)[1][1:]

		file_content = None

		file_name = frappe.db.get_value("File", {"file_url": file_path})
		if file_name:
			file = frappe.get_doc("File", file_name)
			file_content = file.get_content()

		return file_content, extn

	def validate(self):
		file_content = self.check_file()
		self.check_headers(file_content)

	def check_file(self):
		file_content, extn = self.read_file()
		if extn == "xlsx":
			file_content = read_xlsx_file_from_attached_file(fcontent=file_content)
		elif extn == "xls":
			file_content = read_xls_file_from_attached_file(file_content)
		else:
			frappe.throw("Only xls and xlsx files are supported.")
		return file_content
	
	def check_headers(self, file_content):
		get_column_map(file_content)

	def edit_item_supplier(self, data):
		columns = get_column_map(data)
		rows = data[1:]
		limit = 500
		start = 0
		while start < len(rows):
			end = start + limit
			self._edit_item_supplier(rows[start:end], columns)
			start = end

	def _edit_item_supplier(self, data, columns):
		for row in data:
			name = get_cell(row, columns, "Item Supplier Table Name")
			supplier_part_no = get_cell(row, columns, "Supplier Part Number")
			updated_qty = get_cell(row, columns, "Quantity To Update")
			item_code = get_cell(row, columns, "Item Code")

			try:
				updated_qty = str(updated_qty).replace('+', '').strip()
				updated_qty = float(updated_qty)
				if updated_qty > 50:
					updated_qty = 50
			except Exception:
				frappe.log_error(f"Skipping invalid qty {updated_qty} for supplier part number {supplier_part_no}, Item code {item_code}")
				continue

			exists = frappe.db.exists("Item", {"name": item_code})
   
			if exists:
				try:
					item = frappe.get_doc("Item", item_code)
					supplier_exists = False
					for supplier in item.supplier_items:
						if supplier.name == name:
							if not (supplier.ifw_supplier_qoh == updated_qty or (supplier.ifw_supplier_qoh > 49 and updated_qty == 50)):
								supplier.ifw_supplier_qoh = updated_qty
								supplier.ifw_sqohtimestamp = frappe.utils.now_datetime()
								item.save()
								frappe.db.commit()
							supplier_exists = True
							break
					if not supplier_exists:
						frappe.log_error(f"Supplier {name} does not exist for item {item_code}")
	  
				except Exception as e:
					frappe.log_error(f"Error inserting item supplier: {str(e)}")
					frappe.publish_realtime("msgprint", "Error inserting item supplier : " + str(e), user=frappe.session.user)
			else:
				frappe.log_error(f"Item {item_code} does not exist")
				frappe.publish_realtime("msgprint", f"Item {item_code} does not exist", user=frappe.session.user)


@frappe.whitelist(methods=["POST"])
def import_item_supplier():
	uploaded_file = frappe.request.files.get('file')
	if not uploaded_file:
		frappe.throw("No file received")

	# Save file to Frappe
	file_doc = save_file(
		fname=uploaded_file.filename,
		content=uploaded_file.read(),
		dt=None,
		dn=None,
		is_private=True
	)

	item_supplier_import_tool = frappe.get_doc({
		"doctype": "Item Supplier Import Tool",
		"excel_file": file_doc.file_url
	})

	file_content = item_supplier_import_tool.check_file()
	item_supplier_import_tool.check_headers(file_content)
	missing_items_list = validate_item_supplier(file_content)

	# Insert document
	item_supplier_import_tool.insert()

	# Link the file to the doc
	file_doc.reload()
	file_doc.dt = "Item Supplier Import Tool"
	file_doc.dn = item_supplier_import_tool.name
	file_doc.save()

	# Commit before queueing so the background job can load the document
	frappe.db.commit()

	# Updating each Item is too slow to finish within the request timeout,
	# so submit in the background
	item_supplier_import_tool.reload()
	queue_action(item_supplier_import_tool, "submit", timeout=2000, enqueue_after_commit=True)
	frappe.db.commit()

	return {
		"status": "success",
		"queue_status": "Queued",
		"file_url": file_doc.file_url,
		"docname": item_supplier_import_tool.name,
		"missing_items": missing_items_list
	}


REQUIRED_HEADERS = ["Item Supplier Table Name", "Supplier Part Number", "Quantity To Update", "Item Code"]


def get_column_map(data):
	"""Map header names to column indexes. Unknown columns are ignored."""
	if not data:
		frappe.throw("The Excel File is empty.")

	columns = {}
	for idx, header in enumerate(data[0]):
		header = str(header).strip() if header is not None else ""
		if header and header not in columns:
			columns[header] = idx

	missing = [h for h in REQUIRED_HEADERS if h not in columns]
	if missing:
		frappe.throw(f"Missing required header(s) in this Excel File: {', '.join(missing)}")

	return columns


def get_cell(row, columns, header):
	idx = columns[header]
	return row[idx] if idx < len(row) else None


def validate_item_supplier(data):
	columns = get_column_map(data)
	rows = data[1:]
	limit = 500
	start = 0
	all_missing = []

	while start < len(rows):
		end = start + limit
		batch_missing = _validate_item_supplier(rows[start:end], columns)
		all_missing.extend(batch_missing)
		start = end

	return all_missing


def _validate_item_supplier(data, columns):
	missing_list = []

	rows = [
		(get_cell(row, columns, "Item Supplier Table Name"), get_cell(row, columns, "Item Code"))
		for row in data
	]
	names = list({r[0] for r in rows if r[0]})
	item_codes = list({r[1] for r in rows if r[1]})

	# Look up the whole batch in two queries instead of loading every Item
	existing_items = set(frappe.get_all(
		"Item", filters={"name": ["in", item_codes]}, pluck="name"
	)) if item_codes else set()
	existing_suppliers = {
		(d.name, d.parent) for d in frappe.get_all(
			"Item Supplier",
			filters={"name": ["in", names], "parenttype": "Item", "parentfield": "supplier_items"},
			fields=["name", "parent"],
		)
	} if names else set()

	for name, item_code in rows:
		# default values for missing
		item_not_found = None
		supplier_not_found = None

		if item_code not in existing_items:
			item_not_found = item_code
		elif (name, item_code) not in existing_suppliers:
			supplier_not_found = name

		# Only append if any is missing
		if item_not_found or supplier_not_found:
			missing_list.append({
				"item not found": item_not_found,
				"item supplier not found": supplier_not_found
			})

	return missing_list