# Copyright (c) 2026, Techlift Technologies and contributors
# For license information, please see license.txt

import os

import frappe
from frappe import _, msgprint
from frappe.model.docstatus import DocStatus
from frappe.model.document import Document
from frappe.utils.xlsxutils import read_xls_file_from_attached_file, read_xlsx_file_from_attached_file

from metactical.custom_scripts.utils.metactical_utils import queue_action
from metactical.metactical.doctype.item_profile_import_tool.supplier_import import (
	SupplierImporter, get_header_map, get_profile,
)


class ItemProfileImportTool(Document):
	def save(self):
		if self.docstatus == DocStatus.submitted() and \
			self.ais_queue_status and self.ais_queue_status != "Queued":
			msgprint(
				_(
					"The import has been queued as a background job. If anything goes wrong in the \
					background, an error comment is added to this document and it goes back to Draft."
				)
			)
			queue_action(self, "submit", timeout=7200)
		else:
			super().save()

	def validate(self):
		get_header_map(self.read_file(), get_profile(self.supplier))

	def on_submit(self):
		importer = self.run_import(self.read_file())

		# on_submit runs after the child tables were written, so the results go in directly
		self.set("results", [])
		for result in importer.results:
			self.append("results", result).db_insert()
		counts = importer.counts
		self.db_set({
			"total_rows": counts["total"],
			"updated_rows": counts["updated"],
			"unchanged_rows": counts["unchanged"],
			"with_issues_rows": counts["with_issues"],
			"not_imported_rows": counts["not_imported"],
			# The background job loaded this doc while it still said Queued
			"ais_queue_status": "Not Queued",
		}, update_modified=False)

	def run_import(self, data, dry_run=False, sample_size=0):
		profile = get_profile(self.supplier)
		columns = get_header_map(data, profile)
		return SupplierImporter(profile, columns, dry_run=dry_run).run(data[1:], sample_size=sample_size)

	def read_file(self):
		extn = os.path.splitext(self.excel_file or "")[1][1:].lower()
		if extn not in ("xls", "xlsx"):
			frappe.throw(_("Only xls and xlsx files are supported."))

		file_name = frappe.db.get_value("File", {"file_url": self.excel_file})
		if not file_name:
			frappe.throw(_("Could not find the attached file {0}").format(self.excel_file))
		content = frappe.get_doc("File", file_name).get_content()

		if extn == "xlsx":
			return read_xlsx_file_from_attached_file(fcontent=content)
		return read_xls_file_from_attached_file(content)


@frappe.whitelist()
def preview_import(docname):
	"""Run the import without writing anything, for checking a few items first."""
	doc = frappe.get_doc("Item Profile Import Tool", docname)
	doc.check_permission("write")
	importer = doc.run_import(doc.read_file(), dry_run=True, sample_size=10)
	return {
		"counts": importer.counts,
		"samples": importer.samples,
		"results": importer.results[:10],
	}


@frappe.whitelist()
def download_results(docname):
	from frappe.desk.utils import provide_binary_file
	from frappe.utils.xlsxutils import make_xlsx

	doc = frappe.get_doc("Item Profile Import Tool", docname)
	doc.check_permission("read")
	data = [["File Row", "Primary Match Value", "Fallback Match Value", "Item", "Matched By", "Status",
			 "Reason", "What Happened"]]
	data += [[r.row_no, r.match_value, r.fallback_value, r.item_code, r.matched_by, r.status, r.reason,
			  r.action_taken] for r in doc.results]
	provide_binary_file(f"{doc.supplier} import exceptions {doc.name}", "xlsx",
		make_xlsx(data, "Exceptions").getvalue())
