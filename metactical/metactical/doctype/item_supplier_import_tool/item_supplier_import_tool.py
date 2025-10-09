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
	
	def edit_item_supplier(self, data):
		limit = 500
		start = 0
		while start < len(data):
			end = start + limit
			self._edit_item_supplier(data[start:end])
			start = end

	def _edit_item_supplier(self, data):
		for row in data:
			if row[0] == "name":
				continue

			name = row[0]
			updated_qty = row[1]
			parent = row[2]

			try:
				updated_qty = str(updated_qty).replace('+', '').strip()
				updated_qty = int(float(updated_qty))
				if updated_qty > 50:
					updated_qty = 50
			except Exception:
				frappe.log_error(f"Skipping invalid qty {updated_qty} for SKU {name}")
				continue

			exists = frappe.db.exists("Item", {"name": parent})
   
			if exists:
				try:
					item = frappe.get_doc("Item", parent)
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
						frappe.log_error(f"Supplier {name} does not exist for item {parent}")
	  
				except Exception as e:
					frappe.log_error(f"Error inserting item supplier: {str(e)}")
					frappe.publish_realtime("msgprint", "Error inserting item supplier : " + str(e), user=frappe.session.user)
			else:
				frappe.log_error(f"Item {parent} does not exist")
				frappe.publish_realtime("msgprint", f"Item {parent} does not exist", user=frappe.session.user)


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
        "import_based_on": "ERP SKU",
        "excel_file": file_doc.file_url
    })

    file_content = item_supplier_import_tool.check_file()
    missing_items_list = validate_item_supplier(file_content)

    # Insert document
    item_supplier_import_tool.insert()

    # Link the file to the doc
    file_doc.reload()
    file_doc.dt = "Item Supplier Import Tool"
    file_doc.dn = item_supplier_import_tool.name
    file_doc.save()

    item_supplier_import_tool.reload()
    item_supplier_import_tool.submit()
    frappe.db.commit()

    return {
        "status": "success",
        "file_url": file_doc.file_url,
        "docname": item_supplier_import_tool.name,
        "missing_items": missing_items_list
    }


def validate_item_supplier(data):
    limit = 500
    start = 0
    all_missing = []

    while start < len(data):
        end = start + limit
        batch_missing = _validate_item_supplier(data[start:end])
        all_missing.extend(batch_missing)
        start = end

    return all_missing


def _validate_item_supplier(data):
    missing_list = []

    for row in data:
        if row[0] == "name":
            continue

        name = row[0]
        parent = row[2]

        # default values for missing
        item_not_found = None
        supplier_not_found = None

        if not frappe.db.exists("Item", {"name": parent}):
            item_not_found = parent

        try:
            if item_not_found is None:
                item = frappe.get_doc("Item", parent)
                supplier_exists = False
                for supplier in item.supplier_items:
                    if supplier.name == name:
                        supplier_exists = True
                        break
                if not supplier_exists:
                    supplier_not_found = name
        except Exception as e:
            supplier_not_found = name

        # Only append if any is missing
        if item_not_found or supplier_not_found:
            missing_list.append({
                "item not found": item_not_found,
                "item supplier not found": supplier_not_found
            })

    return missing_list