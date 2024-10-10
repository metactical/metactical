import frappe
from erpnext.stock.doctype.packing_slip.packing_slip import PackingSlip
from frappe.utils import cint, flt
from frappe.model import no_value_fields

class CustomPackingSlip(PackingSlip):
	def on_submit(self):
		super(CustomPackingSlip, self).on_submit()
		#Clear associated tote if any
		tote_exists = frappe.db.exists('Picklist Tote', {'current_delivery_note': self.delivery_note})
		if tote_exists:
			docname = frappe.db.get_value('Picklist Tote', {'current_delivery_note': self.delivery_note})
			doc = frappe.get_doc('Picklist Tote', docname)
			doc.update({
				'current_delivery_note': '',
				'used_by': '',
				'tote_items': []
			})
			doc.save(ignore_permissions=True)

	# Metactical Customization: get_items and get_details_for_packing functions have been removed from 
	# version 14 but we maintin them here for the Packing Slip page to work as expected
	@frappe.whitelist()
	def get_items(self):
		self.set("items", [])

		custom_fields = frappe.get_meta("Delivery Note Item").get_custom_fields()

		dn_details = self.get_details_for_packing()[0]
		shipping_items = frappe.get_all('Pick List Shipping Item', pluck='item')
		for item in dn_details:
			if flt(item.qty) > flt(item.packed_qty) and item.item_code not in shipping_items:
				ch = self.append("items", {})
				ch.item_code = item.item_code
				ch.item_name = item.item_name
				ch.stock_uom = item.stock_uom
				ch.dn_detail = item.name
				ch.description = item.description
				ch.batch_no = item.batch_no
				ch.qty = flt(item.qty) - flt(item.packed_qty)

				# copy custom fields
				for d in custom_fields:
					if item.get(d.fieldname):
						ch.set(d.fieldname, item.get(d.fieldname))

		self.update_item_details()

	def get_details_for_packing(self):
		"""
		Returns
		* 'Delivery Note Items' query result as a list of dict
		* Item Quantity dict of current packing slip doc
		* No. of Cases of this packing slip
		"""

		rows = [d.item_code for d in self.get("items")]

		# also pick custom fields from delivery note
		custom_fields = ", ".join(
			"dni.`{0}`".format(d.fieldname)
			for d in frappe.get_meta("Delivery Note Item").get_custom_fields()
			if d.fieldtype not in no_value_fields
		)

		if custom_fields:
			custom_fields = ", " + custom_fields

		condition = ""
		if rows:
			condition = " and item_code in (%s)" % (", ".join(["%s"] * len(rows)))

		# gets item code, qty per item code, latest packed qty per item code and stock uom
		res = frappe.db.sql(
			"""select item_code, sum(qty) as qty, name,
			(select sum(psi.qty * (abs(ps.to_case_no - ps.from_case_no) + 1))
				from `tabPacking Slip` ps, `tabPacking Slip Item` psi
				where ps.name = psi.parent and ps.docstatus = 1
				and ps.delivery_note = dni.parent and psi.item_code=dni.item_code) as packed_qty,
			stock_uom, item_name, description, dni.batch_no {custom_fields}
			from `tabDelivery Note Item` dni
			where parent=%s {condition}
			group by item_code""".format(
				condition=condition, custom_fields=custom_fields
			),
			tuple([self.delivery_note] + rows),
			as_dict=1,
		)

		ps_item_qty = dict([[d.item_code, d.qty] for d in self.get("items")])
		no_of_cases = cint(self.to_case_no) - cint(self.from_case_no) + 1

		return res, ps_item_qty, no_of_cases
	
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
