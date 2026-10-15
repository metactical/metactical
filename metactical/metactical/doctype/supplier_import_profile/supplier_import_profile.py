# Copyright (c) 2026, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

TARGET_DOCTYPES = ("Item", "Item Supplier")

# Field types a file value can sensibly be written into
WRITABLE_TYPES = {
	"Data", "Small Text", "Text", "Long Text", "Text Editor", "Select", "Link", "Float", "Currency",
	"Percent", "Int", "Check", "Date", "Datetime",
}

# Never written by an import: they identify the record, or the import manages them itself
PROTECTED_FIELDS = {
	"Item": {"item_code", "naming_series", "variant_of", "has_variants"},
	"Item Supplier": {"supplier"},
}


def get_target_fields(doctype):
	"""{fieldname: label} for every field of `doctype` a profile may map a column to."""
	if doctype not in TARGET_DOCTYPES:
		return {}
	protected = PROTECTED_FIELDS.get(doctype, set())
	return {
		df.fieldname: _(df.label or df.fieldname)
		for df in frappe.get_meta(doctype).fields
		if df.fieldtype in WRITABLE_TYPES and df.fieldname not in protected and not df.read_only
	}


@frappe.whitelist()
def search_target_fields(txt=None, target_doctype=None, **kwargs):
	"""Target Field dropdown: match on the label people see, show the fieldname alongside."""
	txt = (txt or "").lower()
	fields = get_target_fields(target_doctype)
	out = [
		{"value": fieldname, "label": f"{label} ({fieldname})"}
		for fieldname, label in fields.items()
		if txt in label.lower() or txt in fieldname
	]
	return sorted(out, key=lambda o: (not o["label"].lower().startswith(txt), o["label"]))[:50]


class SupplierImportProfile(Document):
	def validate(self):
		self.primary_match_column = (self.primary_match_column or "").strip()
		self.fallback_match_column = (self.fallback_match_column or "").strip()
		if not self.fallback_match_on:
			self.fallback_match_column = ""
		elif self.fallback_match_on == self.primary_match_on:
			frappe.throw(_("Fallback Match On must be different from Primary Match On."))

		seen = set()
		for row in self.mappings:
			row.file_column = (row.file_column or "").strip()
			fields = get_target_fields(row.target_doctype)
			if row.target_field not in fields:
				frappe.throw(_("Row {0}: pick a Target Field from the list for {1}").format(row.idx, row.target_doctype))
			row.target_field_label = fields[row.target_field]
			key = (row.target_doctype, row.target_field)
			if key in seen:
				frappe.throw(_("Row {0}: {1} - {2} is mapped more than once").format(
					row.idx, row.target_doctype, row.target_field_label))
			seen.add(key)
			if row.target_doctype == "Item Supplier" and row.target_field == "supplier_part_no" \
					and "Supplier Part Number" in (self.primary_match_on, self.fallback_match_on):
				frappe.throw(_("Row {0}: the supplier part number already comes from the match column, "
							   "remove this mapping").format(row.idx))

	def required_columns(self):
		columns = [self.primary_match_column]
		if self.fallback_match_on:
			columns.append(self.fallback_match_column)
		return columns + [row.file_column for row in self.mappings]
