# Copyright (c) 2026, Storebuilder Commerce Inc and contributors
# For license information, please see license.txt

"""Printing a Purchase Order V3 with the native Purchase Order layouts.

Every PO print format is written against native Purchase Order fields -- taxes,
grand_total, contact_person, terms, transaction_date, ... -- which PO3 does not
have. Each "<format> - PO3" print format is a copy of a native one that renders
against po3_print_doc(doc) instead of the PO3 itself: an UNSAVED Purchase Order
whose header, lines, taxes and discount come from the PO3, and whose contact,
terms and the rest come from the PO3's native twin (erp_purchase_order). Nothing here
writes to the database.

    Jinja formats    {%- set doc = po3_print_doc(doc) -%} + the native template
    Builder formats  po3_render_builder(...), which lays out the native format's
                     builder data (kept in the PO3 format's own format_data)
                     with Purchase Order's meta, as Frappe's standard.html does
"""

import json

import frappe
from frappe.www.printview import make_layout, set_link_titles, standard_format
from markupsafe import Markup

from metactical.procurement_v3.taxes import copy_taxes_to_native
from metactical.procurement_v3.utils import F


def po3_print_doc(doc):
	"""The PO3 as a Purchase Order, for printing. See the module docstring."""
	if isinstance(doc, str):
		doc = frappe.get_doc("Purchase Order V3", doc)
	if doc.doctype != "Purchase Order V3":
		return doc
	if doc.flags.po3_print_doc:
		return doc.flags.po3_print_doc

	from metactical.metactical.doctype.purchase_order_v3.purchase_order_v3 import (
		copy_line_identifiers,
		po_ship_date,
		set_native_addresses,
	)

	twin = doc.erp_purchase_order
	if twin and not frappe.db.exists("Purchase Order", twin):
		twin = None
	npo = frappe.get_doc("Purchase Order", twin) if twin else frappe.new_doc("Purchase Order")
	twin_rows = {r.name: r for r in npo.get("items")}
	# erp_po_item is only stamped at approval; before that, pair lines by item
	unpaired = list(npo.get("items"))

	# the number the supplier knows the order by -- the same one the email uses
	npo.name = twin or doc.name
	npo.docstatus = doc.docstatus
	npo.supplier = doc.supplier
	npo.supplier_name = doc.supplier_name
	npo.company = doc.company
	npo.transaction_date = doc.order_date
	npo.schedule_date = po_ship_date(doc)
	npo.ais_cancel_date = doc.required_by
	npo.currency = doc.currency
	npo.conversion_rate = F(doc.conversion_rate) or 1
	npo.buying_price_list = doc.buying_price_list
	npo.set_warehouse = doc.set_warehouse
	npo.custom_purchase_order_v3 = doc.name
	set_native_addresses(npo, doc)
	copy_taxes_to_native(npo, doc)
	if doc.notes_to_supplier:
		npo.drop_ship_notes = doc.notes_to_supplier

	npo.set("items", [])
	for d in doc.items:
		if d.line_status == "Cancelled":
			continue
		old = twin_rows.get(d.erp_po_item) \
			or next((r for r in unpaired if r.item_code == d.item_code), None)
		if old in unpaired:
			unpaired.remove(old)
		r = npo.append("items", old.as_dict(no_default_fields=True) if old else {})
		item = frappe.get_cached_value("Item", d.item_code,
			["item_name", "description", "stock_uom", "image", "ifw_location", "ifw_retailskusuffix"],
			as_dict=True) or frappe._dict()
		r.item_code = d.item_code
		r.item_name = d.item_name or item.item_name
		r.description = r.description or item.description or r.item_name
		r.image = r.image or item.image
		r.stock_uom = r.stock_uom or item.stock_uom
		r.uom = d.uom or r.uom or r.stock_uom
		if not old or r.uom != old.uom:
			r.conversion_factor = 1 if r.uom == r.stock_uom else F(frappe.db.get_value(
				"UOM Conversion Detail", {"parent": d.item_code, "uom": r.uom}, "conversion_factor")) or 1
		r.qty = F(d.qty)
		r.stock_qty = r.qty * F(r.conversion_factor or 1)
		r.rate = F(d.rate)
		r.amount = r.qty * r.rate
		r.warehouse = d.warehouse or doc.set_warehouse
		# as the approval sync does: every line ships on the PO's ship date
		r.schedule_date = npo.schedule_date
		r.material_request = d.material_request
		r.material_request_item = d.material_request_item
		r.ifw_location = r.ifw_location or item.ifw_location
		r.ifw_retailskusuffix = d.retail_sku_suffix or item.ifw_retailskusuffix
		r.item_tax_rate = r.item_tax_rate or "{}"
		# the PO3 line's own identifiers, but a blank one keeps the twin's
		barcode, part_no = r.barcode, r.supplier_part_no
		copy_line_identifiers(r, d)
		r.barcode = r.barcode or barcode
		r.supplier_part_no = r.supplier_part_no or part_no

	# Taxes are the PO3's own (copy_taxes_to_native above); work them and the
	# totals out for the PO3's lines.
	try:
		npo.calculate_taxes_and_totals()
		npo.set_total_in_words()
	except Exception:
		frappe.clear_last_message()
		npo.total_qty = sum(F(r.qty) for r in npo.items)
		npo.total = npo.net_total = sum(F(r.amount) for r in npo.items)
		npo.grand_total = npo.rounded_total = npo.total + F(npo.total_taxes_and_charges)

	doc.flags.po3_print_doc = npo
	return npo


def po3_print_items(doc):
	"""get_po_items for a PO3 print: lines merged by item, read from the print
	doc itself rather than from a saved Purchase Order."""
	items, by_code = [], {}
	for row in po3_print_doc(doc).items:
		if row.item_code in by_code:
			by_code[row.item_code].qty += row.qty
		else:
			by_code[row.item_code] = row
			items.append(row)
	return items


def po3_render_builder(doc, print_format, no_letterhead=None, letter_head=None, footer=None,
		print_settings=None):
	"""Render a builder layout copied from a native PO format against the print
	doc, the way frappe.www.printview.get_rendered_template does for builder
	formats -- but with Purchase Order's meta, which the layout was made for."""
	pf = frappe.get_cached_doc("Print Format", print_format)
	npo = po3_print_doc(doc)
	print_settings = print_settings or frappe.get_single("Print Settings").as_dict()

	npo.flags.in_print = True
	npo.flags.print_settings = print_settings
	npo.run_method("before_print", print_settings)
	npo.print_heading = getattr(npo, "print_heading", None)
	npo.sub_heading = getattr(npo, "sub_heading", None)
	npo.print_section_headings = pf.show_section_headings
	npo.print_line_breaks = pf.line_breaks
	npo.align_labels_right = pf.align_labels_right
	npo.absolute_value = pf.absolute_value

	format_data, format_data_map = json.loads(pf.format_data or "[]"), {}
	for df in format_data:
		format_data_map[df.get("fieldname")] = df
		for col in df.get("visible_columns") or []:
			format_data_map[col.get("fieldname")] = col
	npo.format_data_map = format_data_map

	heading = None
	if format_data and format_data[0].get("fieldname") == "print_heading_template":
		heading = format_data.pop(0).get("options")

	meta = frappe.get_meta("Purchase Order")
	set_link_titles(npo)
	html = frappe.get_jenv().get_template(standard_format).render({
		"doc": npo,
		"meta": meta,
		"layout": make_layout(npo, meta, format_data),
		"no_letterhead": no_letterhead,
		"trigger_print": 0,
		"letter_head": letter_head,
		"footer": footer,
		"print_settings": print_settings,
		"print_heading_template": heading,
	})
	return Markup(html)
