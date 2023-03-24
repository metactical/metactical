# Copyright (c) 2023, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe import _
from frappe.model import no_value_fields
from frappe.utils import cint, flt

class STEPackingSlip(Document):
	def validate(self):
		self.validate_stock_entry()
		self.validate_case_nos()
	
	def validate_stock_entry(self):
		"""
		Validates if stock entry has status as draft
		"""
		if cint(frappe.db.get_value("Stock Entry", self.stock_entry, "docstatus")) != 0:
			frappe.throw(_("Stock Entry {0} must not be submitted").format(self.stock_entry))
			
	def validate_case_nos(self):
		"""
		Validate if case nos overlap. If they do, recommend next case no.
		"""
		if not cint(self.from_case_no):
			frappe.msgprint(_("Please specify a valid 'From Case No.'"), raise_exception=1)
		elif not self.to_case_no:
			self.to_case_no = self.from_case_no
		elif cint(self.from_case_no) > cint(self.to_case_no):
			frappe.msgprint(_("'To Case No.' cannot be less than 'From Case No.'"), raise_exception=1)

		res = frappe.db.sql(
			"""SELECT name FROM `tabSTE Packing Slip`
			WHERE stock_entry = %(stock_entry)s AND docstatus = 1 AND
			((from_case_no BETWEEN %(from_case_no)s AND %(to_case_no)s)
			OR (to_case_no BETWEEN %(from_case_no)s AND %(to_case_no)s)
			OR (%(from_case_no)s BETWEEN from_case_no AND to_case_no))
			""",
			{
				"stock_entry": self.stock_entry,
				"from_case_no": self.from_case_no,
				"to_case_no": self.to_case_no,
			},
		)

		if res:
			frappe.throw(
				_("""Case No(s) already in use. Try from Case No {0}""").format(self.get_recommended_case_no())
			)
			
	def get_details_for_packing(self):
		"""
		Returns
		* 'Stock Entry Detail' query result as a list of dict
		* Item Quantity dict of current packing slip doc
		* No. of Cases of this packing slip
		"""

		rows = [d.item_code for d in self.get("items")]

		# also pick custom fields from stock entry
		custom_fields = ", ".join(
			"dni.`{0}`".format(d.fieldname)
			for d in frappe.get_meta("Stock Entry Detail").get_custom_fields()
			if d.fieldtype not in no_value_fields
		)

		if custom_fields:
			custom_fields = ", " + custom_fields

		condition = ""
		if rows:
			condition = " and item_code in (%s)" % (", ".join(["%s"] * len(rows)))

		# gets item code, qty per item code, latest packed qty per item code and stock uom
		res = frappe.db.sql(
			"""select item_code, sum(qty) as qty,
			(select sum(psi.qty * (abs(ps.to_case_no - ps.from_case_no) + 1))
				from `tabSTE Packing Slip` ps, `tabSTE Packing Slip Item` psi
				where ps.name = psi.parent and ps.docstatus = 1
				and ps.stock_entry = dni.parent and psi.item_code=dni.item_code) as packed_qty,
			stock_uom, item_name, description, dni.batch_no {custom_fields}
			from `tabStock Entry Detail` dni
			where parent=%s {condition}
			group by item_code""".format(
				condition=condition, custom_fields=custom_fields
			),
			tuple([self.stock_entry] + rows),
			as_dict=1,
		)

		ps_item_qty = dict([[d.item_code, d.qty] for d in self.get("items")])
		no_of_cases = cint(self.to_case_no) - cint(self.from_case_no) + 1

		return res, ps_item_qty, no_of_cases
			
	@frappe.whitelist()
	def get_items(self):
		self.set("items", [])

		custom_fields = frappe.get_meta("Stock Entry Detail").get_custom_fields()

		ste_details = self.get_details_for_packing()[0]
		for item in ste_details:
			if flt(item.qty) > flt(item.packed_qty):
				ch = self.append("items", {})
				ch.item_code = item.item_code
				ch.item_name = item.item_name
				ch.stock_uom = item.stock_uom
				ch.description = item.description
				ch.batch_no = item.batch_no
				ch.qty = flt(item.qty) - flt(item.packed_qty)

				# copy custom fields
				for d in custom_fields:
					if item.get(d.fieldname):
						ch.set(d.fieldname, item.get(d.fieldname))

		self.update_item_details()
		
	def update_item_details(self):
		"""
		Fill empty columns in Packing Slip Item
		"""
		if not self.from_case_no:
			self.from_case_no = self.get_recommended_case_no()

		for d in self.get("items"):
			res = frappe.db.get_value("Item", d.item_code, ["weight_per_unit", "weight_uom"], as_dict=True)

			if res and len(res) > 0:
				d.net_weight = res["weight_per_unit"]
				d.weight_uom = res["weight_uom"]
	
	def get_recommended_case_no(self):
		"""
		Returns the next case no. for a new packing slip for a stock
		entry
		"""
		recommended_case_no = frappe.db.sql(
			"""SELECT MAX(to_case_no) FROM `tabSTE Packing Slip`
			WHERE stock_entry = %s AND docstatus=1""",
			self.stock_entry,
		)

		return cint(recommended_case_no[0][0]) + 1
	
@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def item_details(doctype, txt, searchfield, start, page_len, filters):
	from erpnext.controllers.queries import get_match_cond

	return frappe.db.sql(
		"""select name, item_name, description from `tabItem`
				where name in ( select item_code FROM `tabDStock Entry Detail`
	 						where parent= %s)
	 			and %s like "%s" %s
	 			limit  %s, %s """
		% ("%s", searchfield, "%s", get_match_cond(doctype), "%s", "%s"),
		((filters or {}).get("stock_entry"), "%%%s%%" % txt, start, page_len),
	)
