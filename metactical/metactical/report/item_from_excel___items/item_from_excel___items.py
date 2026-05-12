# Copyright (c) 2026, Storebuilder Commerce Inc and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, get_url
from erpnext.setup.utils import get_exchange_rate

# Price list names (exact, as used elsewhere in the metactical codebase)
PL_CAMO = "RET - Camo"
PL_GPD = "RET - GPD"
PL_CAMO_FRN = "RET - CamoFRN - USD"


def execute(filters=None):
	"""Script-report entry point. Returns `(columns, data)` for the desk UI."""
	filters = filters or {}
	item_from_excel = filters.get("item_from_excel")

	if not item_from_excel:
		return get_columns(), []

	doc = frappe.get_doc("Item From Excel", item_from_excel)

	# Status gate: only show data once the doc has been submitted.
	check_import_status(doc)

	# Re-parse the attached excel to find the variant item codes that were imported
	item_codes = get_item_codes_from_excel(doc)
	if not item_codes:
		return get_columns(), []

	# One exchange rate lookup for the whole report
	try:
		usd_to_cad = flt(get_exchange_rate("USD", "CAD")) or 0
	except Exception:
		usd_to_cad = 0

	data = build_rows(item_codes, usd_to_cad)
	return get_columns(), data


def _response(status, message, item_from_excel, columns=None, data=None):
	"""Single source of truth for the API envelope shape."""
	return {
		"success": status == "ok",
		"status": status,
		"message": message,
		"item_from_excel": item_from_excel,
		"columns": columns or [],
		"data": data or [],
	}


@frappe.whitelist()
def get_report(item_from_excel=None):
	if not item_from_excel:
		return _response(
			"error",
			_("Missing required parameter: item_from_excel"),
			item_from_excel,
		)

	if not frappe.db.exists("Item From Excel", item_from_excel):
		return _response(
			"not_found",
			_("Item From Excel {0} does not exist.").format(item_from_excel),
			item_from_excel,
		)

	# Reuse the existing docstatus check via the doc we'll need anyway
	doc = frappe.get_doc("Item From Excel", item_from_excel)
	if doc.docstatus != 1:
		return _response(
			"not_submitted",
			_("Item From Excel {0} has not been submitted yet. Submit the document to start the import.").format(item_from_excel),
			item_from_excel,
		)

	try:
		columns, data = execute({"item_from_excel": item_from_excel})
	except Exception as exc:
		# Anything that slips past the explicit checks above (e.g. excel parse
		# failure, DB error) gets a uniform error envelope.
		frappe.log_error(
			title="Item From Excel - Items: get_report failed",
			message=frappe.get_traceback(),
		)
		return _response("error", str(exc), item_from_excel)

	return _response(
		"ok",
		_("Report ready."),
		item_from_excel,
		columns=columns,
		data=data,
	)


def check_import_status(doc):
	"""Refuse to render the report unless the source doc is submitted."""
	if doc.docstatus != 1:
		frappe.throw(
			_("Item From Excel <b>{0}</b> has not been submitted yet. Submit the document to start the import.")
			.format(doc.name)
		)


def get_item_codes_from_excel(doc):
	"""
	Re-read the attached excel and pull the variant item codes.

	Reuses `ItemFromExcel.check_file()` which already returns cleaned sheet data
	in the form [template_sheet, variant_sheet, specs_sheet].

	Item codes for this report come from the Variant sheet (one row per variant).
	"""
	if not doc.excel_file:
		return []

	try:
		sheets = doc.check_file()
	except Exception:
		# If the file is missing/unreadable we surface an empty result rather than
		# blowing up the report - the user can still see the failure on the doc.
		frappe.log_error(
			title="Item From Excel - Items: failed to re-parse excel",
			message=frappe.get_traceback(),
		)
		return []

	if not sheets or len(sheets) < 2:
		return []

	variant_sheet = sheets[1]
	if not variant_sheet:
		return []

	headers = variant_sheet[0]
	if "Item Code" not in headers:
		return []

	idx = headers.index("Item Code")
	item_codes = []
	seen = set()
	for row in variant_sheet[1:]:
		if len(row) <= idx:
			continue
		value = row[idx]
		if value is None:
			continue
		code = str(value).strip()
		if code and code not in seen:
			seen.add(code)
			item_codes.append(code)
	return item_codes


def get_price_list_currencies(price_lists):
	"""Return {price_list_name: currency} for each name. Defaults to CAD if missing."""
	rows = frappe.db.get_all(
		"Price List",
		filters={"name": ("in", list(price_lists))},
		fields=["name", "currency"],
	)
	currencies = {r["name"]: (r.get("currency") or "CAD").upper() for r in rows}
	# Fall back to CAD for any list not in the table so the report still renders
	for pl in price_lists:
		currencies.setdefault(pl, "CAD")
	return currencies


def build_rows(item_codes, usd_to_cad):
	"""Fetch item details + prices and compute the derived margin/cost columns."""
	# Resolve the currency of each retail price list once (drives margin cost basis)
	price_list_currencies = get_price_list_currencies([PL_CAMO, PL_GPD, PL_CAMO_FRN])

	# Pull all needed Item fields in one query. Exclude templates (`has_variants = 1`)
	# so only variant rows make it to the report.
	items = frappe.db.sql(
		"""
		SELECT
			name, item_code, item_name, item_group, brand, image,
			variant_of, ifw_retailskusuffix, ifw_duty_rate, creation
		FROM `tabItem`
		WHERE name IN %(codes)s
		  AND COALESCE(has_variants, 0) = 0
		""",
		{"codes": tuple(item_codes)},
		as_dict=True,
	)
	items_by_code = {it["name"]: it for it in items}

	# First supplier_part_no per item
	supplier_rows = frappe.db.sql(
		"""
		SELECT parent, supplier_part_no
		FROM `tabItem Supplier`
		WHERE parent IN %(codes)s
		ORDER BY idx ASC
		""",
		{"codes": tuple(item_codes)},
		as_dict=True,
	)
	supplier_part_no_by_code = {}
	for r in supplier_rows:
		supplier_part_no_by_code.setdefault(r["parent"], r.get("supplier_part_no"))

	# Item Prices we care about: the three retail price lists + supplier (buying) cost
	# (the supplier cost lives in any "SUP - …" buying price list).
	prices = frappe.db.sql(
		"""
		SELECT item_code, price_list, price_list_rate, currency, buying, modified
		FROM `tabItem Price`
		WHERE item_code IN %(codes)s
		  AND (
		        price_list IN %(retail)s
		     OR (buying = 1 AND price_list LIKE 'SUP - %%')
		  )
		ORDER BY modified DESC
		""",
		{
			"codes": tuple(item_codes),
			"retail": (PL_CAMO, PL_GPD, PL_CAMO_FRN),
		},
		as_dict=True,
	)

	# Index retail prices and resolve the supplier cost per item. Rows are sorted
	# DESC by `modified`, so the first SUP - row we see for a given item is the
	# most recent one (the deterministic tie-break the plan calls for).
	retail_by_item = {}
	supplier_cost_by_item = {}  # code -> (rate, currency)
	for p in prices:
		code = p["item_code"]
		pl = p["price_list"]
		rate = p["price_list_rate"]

		if pl in (PL_CAMO, PL_GPD, PL_CAMO_FRN):
			retail_by_item.setdefault(code, {})[pl] = rate
			continue

		if p.get("buying") and pl and pl.startswith("SUP - "):
			supplier_cost_by_item.setdefault(code, (rate, (p.get("currency") or "").upper()))

	# Cache USD<-other-currency conversions across the whole report
	to_usd_rate_cache = {"USD": 1.0}

	def to_usd(amount, currency):
		"""Convert `amount` from `currency` to USD. Returns 0 on missing data."""
		amount = flt(amount)
		if not amount:
			return 0
		currency = (currency or "USD").upper()
		if currency not in to_usd_rate_cache:
			try:
				to_usd_rate_cache[currency] = flt(get_exchange_rate(currency, "USD")) or 0
			except Exception:
				to_usd_rate_cache[currency] = 0
		rate = to_usd_rate_cache[currency]
		return amount * rate if rate else 0

	rows = []
	for code in item_codes:
		item = items_by_code.get(code)
		if not item:
			# Either a template (filtered out of the SQL above) or an item that
			# hasn't been created yet - skip it entirely.
			continue

		duty_rate = flt(item.get("ifw_duty_rate"))

		cost_row = supplier_cost_by_item.get(code)
		if cost_row:
			raw_rate, raw_currency = cost_row
			supplier_cost_usd = to_usd(raw_rate, raw_currency)
		else:
			supplier_cost_usd = 0

		retail_prices = retail_by_item.get(code, {})
		ret_camo = flt(retail_prices.get(PL_CAMO))
		ret_gpd = flt(retail_prices.get(PL_GPD))
		ret_camofrn_usd = flt(retail_prices.get(PL_CAMO_FRN))

		# Derived columns - mirror the user's IFERROR formulas. Anything that
		# divides by zero / works on None becomes blank, exactly like IFERROR.
		# `ifw_duty_rate` is stored as a whole-number percent (matches existing
		# reports, see sales_report___for_admins.py), so divide by 100 here.
		cost_usd_landed = safe_mul(supplier_cost_usd, 1 + (duty_rate / 100.0))
		cost_cad_landed = safe_mul(cost_usd_landed, usd_to_cad)

		# Each retail price list has its own currency on the Price List doctype.
		# Pick the cost basis that matches that currency: USD -> Cost USD (landed),
		# anything else (CAD) -> Cost CAD (landed).
		def cost_basis_for(price_list_name):
			currency = price_list_currencies.get(price_list_name, "CAD")
			return cost_usd_landed if currency == "USD" else cost_cad_landed

		margin_camo = safe_margin(ret_camo, cost_basis_for(PL_CAMO))
		margin_gpd = safe_margin(ret_gpd, cost_basis_for(PL_GPD))
		margin_camofrn = safe_margin(ret_camofrn_usd, cost_basis_for(PL_CAMO_FRN))

		# Image: store the absolute URL so it works for both UI rendering and API consumers.
		# `Item.image` is usually a site-relative path like "/files/foo.jpg".
		raw_image = item.get("image") or ""
		if raw_image and raw_image.startswith("/"):
			image = get_url(raw_image)
		else:
			image = raw_image  # already absolute (http(s)://...) or empty

		rows.append({
			"image": image,
			"erpsku": item["name"],
			"retail_sku": item.get("ifw_retailskusuffix"),
			"template_sku": item.get("variant_of"),
			"item_name": item.get("item_name"),
			"item_group": item.get("item_group"),
			"brand": item.get("brand"),
			"supplier_part_no": supplier_part_no_by_code.get(code),
			"date_created": item.get("creation"),
			"duty_rate": duty_rate,
			"supplier_cost_usd": supplier_cost_usd or None,
			"cost_usd_landed": cost_usd_landed,
			"cost_cad_landed": cost_cad_landed,
			"ret_camo": ret_camo or None,
			"margin_camo": margin_camo,
			"ret_gpd": ret_gpd or None,
			"margin_gpd": margin_gpd,
			"ret_camofrn_usd": ret_camofrn_usd or None,
			"margin_camofrn": margin_camofrn,
			# Display-only - blank for export
			"status": "",
			"updated_by": "",
			"notes": "",
		})

	return rows


def safe_mul(a, b):
	"""Return a*b, or None if the inputs are missing/zero on the cost side."""
	a = flt(a)
	b = flt(b)
	if not a or not b:
		return None
	return a * b


def safe_margin(retail, cost):
	"""IFERROR((retail - cost) / cost, '') - blank if cost is missing/zero or retail missing.

	Frappe's `Percent` fieldtype renders whole numbers (25 -> "25%"), so we
	scale the fraction by 100 before returning.
	"""
	retail = flt(retail)
	cost = flt(cost)
	if not retail or not cost:
		return None
	try:
		return ((retail - cost) / cost) * 100
	except ZeroDivisionError:
		return None


def get_columns():
	return [
		{"fieldname": "image", "label": _("Image"), "fieldtype": "Data", "width": 240},
		{"fieldname": "erpsku", "label": _("ERPSKU"), "fieldtype": "Link", "options": "Item", "width": 140},
		{"fieldname": "retail_sku", "label": _("Retail SKU"), "fieldtype": "Data", "width": 140},
		{"fieldname": "template_sku", "label": _("Template SKU"), "fieldtype": "Link", "options": "Item", "width": 140},
		{"fieldname": "item_name", "label": _("Item Name"), "fieldtype": "Data", "width": 220},
		{"fieldname": "item_group", "label": _("Item Group"), "fieldtype": "Link", "options": "Item Group", "width": 140},
		{"fieldname": "brand", "label": _("Item Brand"), "fieldtype": "Link", "options": "Brand", "width": 120},
		{"fieldname": "supplier_part_no", "label": _("Supplier Part #"), "fieldtype": "Data", "width": 140},
		{"fieldname": "date_created", "label": _("Date Created"), "fieldtype": "Date", "width": 110},
		{"fieldname": "duty_rate", "label": _("Duty Rate"), "fieldtype": "Percent", "width": 90},
		{"fieldname": "supplier_cost_usd", "label": _("Supplier Cost (USD)"), "fieldtype": "Currency", "options": "USD", "width": 130},
		{"fieldname": "cost_usd_landed", "label": _("Cost USD (landed)"), "fieldtype": "Currency", "options": "USD", "width": 130},
		{"fieldname": "cost_cad_landed", "label": _("Cost CAD (landed)"), "fieldtype": "Currency", "options": "CAD", "width": 130},
		{"fieldname": "ret_camo", "label": _("RET - Camo"), "fieldtype": "Currency", "options": "CAD", "width": 110},
		{"fieldname": "margin_camo", "label": _("Margin Camo"), "fieldtype": "Percent", "width": 100},
		{"fieldname": "ret_gpd", "label": _("RET - GPD"), "fieldtype": "Currency", "options": "CAD", "width": 110},
		{"fieldname": "margin_gpd", "label": _("Margin GPD"), "fieldtype": "Percent", "width": 100},
		{"fieldname": "ret_camofrn_usd", "label": _("RET - CamoFRN (USD)"), "fieldtype": "Currency", "options": "USD", "width": 140},
		{"fieldname": "margin_camofrn", "label": _("Margin CamoFRN"), "fieldtype": "Percent", "width": 110},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
		{"fieldname": "updated_by", "label": _("Updated By"), "fieldtype": "Data", "width": 140},
		{"fieldname": "notes", "label": _("Notes"), "fieldtype": "Small Text", "width": 200},
	]
