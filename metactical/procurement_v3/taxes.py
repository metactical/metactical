# Copyright (c) 2026, Storebuilder Commerce Inc and contributors
# For license information, please see license.txt

"""Taxes and Charges, Totals and Additional Discount on Purchase Order V3 and
Supplier Order Confirmation V3.

Both doctypes carry the native Purchase Order's own fields for these, under the
same names, and its own child table (Purchase Taxes and Charges). The numbers
are not worked out here: set_v3_totals hands the lines and tax rows to ERPNext's
calculate_taxes_and_totals on an unsaved Purchase Order and copies the results
back -- so a PO3 shows exactly what its native twin will, for every charge type,
the additional discount and rounding. Nothing here writes to the database.
"""

import frappe
from erpnext.controllers.accounts_controller import get_taxes_and_charges
from erpnext.controllers.taxes_and_totals import calculate_taxes_and_totals

from metactical.procurement_v3.utils import F

# What the user sets; carried onto the native twin and onto a new SOC3.
TAX_SETTINGS = ("tax_category", "taxes_and_charges", "apply_discount_on",
	"additional_discount_percentage", "discount_amount", "disable_rounded_total")

# What calculate_taxes_and_totals works out.
TOTAL_FIELDS = ("base_total", "net_total", "base_net_total",
	"taxes_and_charges_added", "base_taxes_and_charges_added",
	"taxes_and_charges_deducted", "base_taxes_and_charges_deducted",
	"total_taxes_and_charges", "base_total_taxes_and_charges",
	"discount_amount", "base_discount_amount",
	"grand_total", "base_grand_total",
	"rounding_adjustment", "base_rounding_adjustment", "rounded_total", "base_rounded_total")

TAX_ROW_TOTALS = ("tax_amount", "base_tax_amount", "tax_amount_after_discount_amount",
	"base_tax_amount_after_discount_amount", "total", "base_total", "item_wise_tax_detail")


def tax_rows(doc):
	return [t.as_dict(no_default_fields=True) for t in doc.get("taxes") or []]


def fill_taxes_from_template(doc):
	"""As ERPNext does on a new transaction: no rows yet but a template chosen
	(or the company's default template) -> the template's rows."""
	if doc.get("taxes"):
		return
	if doc.is_new() and not doc.taxes_and_charges and doc.company:
		doc.taxes_and_charges = frappe.db.get_value("Purchase Taxes and Charges Template",
			{"is_default": 1, "company": doc.company, "disabled": 0})
	if doc.taxes_and_charges:
		doc.set("taxes", get_taxes_and_charges("Purchase Taxes and Charges Template", doc.taxes_and_charges))


def prepare_tax_rows(doc):
	"""Description and cost center are mandatory on a tax row; the native form
	fills them from the account and the company, so do the same here."""
	cost_center = frappe.get_cached_value("Company", doc.company, "cost_center") if doc.company else None
	for t in doc.get("taxes") or []:
		if t.account_head and not t.description:
			t.description = t.account_head.rsplit(" - ", 1)[0]
		t.cost_center = t.cost_center or cost_center
		t.category = t.category or "Total"
		t.add_deduct_tax = t.add_deduct_tax or "Add"


def set_v3_totals(doc, lines):
	"""Work out taxes and totals for `doc` (PO3 or SOC3) over `lines`, a list of
	(item_code, qty, rate) -- the quantities that count towards the order.

	Sets doc.total too, and the computed amounts on each of doc.taxes."""
	prepare_tax_rows(doc)
	npo = frappe.new_doc("Purchase Order")
	npo.company = doc.company
	npo.supplier = doc.supplier
	npo.currency = doc.currency
	npo.conversion_rate = F(doc.conversion_rate) or 1
	npo.price_list_currency = doc.currency
	npo.plc_conversion_rate = npo.conversion_rate
	for f in TAX_SETTINGS:
		npo.set(f, doc.get(f))
	for item_code, qty, rate in lines:
		npo.append("items", {"item_code": item_code, "qty": F(qty), "rate": F(rate),
			"price_list_rate": F(rate), "conversion_factor": 1, "item_tax_rate": "{}"})
	npo.set("taxes", tax_rows(doc))

	calculate_taxes_and_totals(npo)

	doc.total = npo.total
	for f in TOTAL_FIELDS:
		doc.set(f, npo.get(f))
	for mine, calc in zip(doc.get("taxes") or [], npo.taxes):
		for f in TAX_ROW_TOTALS:
			mine.set(f, calc.get(f))


def copy_taxes_to_native(npo, doc):
	"""The PO3's taxes and discount onto its native twin, replacing the twin's."""
	for f in TAX_SETTINGS:
		npo.set(f, doc.get(f))
	# tax_amount stays: on an Actual charge it is what the user typed, not a result
	npo.set("taxes", [{k: v for k, v in t.items() if k == "tax_amount" or k not in TAX_ROW_TOTALS}
		for t in tax_rows(doc)])


def save_v3_totals(doc):
	"""For a submitted doc whose totals were just recomputed: write the header
	totals and each tax row's amounts straight to the database."""
	frappe.db.set_value(doc.doctype, doc.name, {f: doc.get(f) for f in ("total",) + TOTAL_FIELDS},
		update_modified=False)
	for t in doc.get("taxes") or []:
		frappe.db.set_value(t.doctype, t.name, {f: t.get(f) for f in TAX_ROW_TOTALS},
			update_modified=False)
