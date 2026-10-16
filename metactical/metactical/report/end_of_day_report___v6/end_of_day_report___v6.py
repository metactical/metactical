# Copyright (c) 2026, Storebuilder Commerce Inc and contributors
# For license information, please see license.txt

import frappe
from datetime import datetime
from dateutil.relativedelta import relativedelta
from metactical.metactical.report.end_of_day_report___v5.end_of_day_report___v5 import (
	get_website_orders_sql,
)

_EXCLUDED_SOURCES = ["Website - Valley", "Website - MRK", "Website - Zelen", "Store - Camo - Montreal"]

_CA_STORES_ORDER = [
	"Store - Camo - Downtown",
	"Store - Camo - Edmonds",
	"Store - Camo - Victoria",
	"Store - Camo - Queen",
	"Store - Gorilla - Vancouver",
]

_CA_WEB_ORDER = ["Website - RAS", "Website - Camo", "Website - Gorilla", "Website - GPD"]


def execute(filters=None):
	if not filters:
		filters = {}

	date = filters.get("date")
	if not date:
		return get_columns(), []

	closings = frappe.db.get_all(
		"End of Day Closing",
		filters={"closing_date": date, "docstatus": 1},
		fields=[
			"name", "lead_source", "user", "user_name",
			"mop_total_expected", "mop_total_actual", "mop_total_difference",
			"closing_notes", "closing_time",
		],
		order_by="lead_source asc, closing_time asc",
	)

	store_closings = {}
	for c in closings:
		src = c.lead_source or "Unknown"
		store_closings.setdefault(src, []).append(c)

	data = []

	# ── CA section ───────────────────────────────────────────────────────────
	default_company = frappe.db.get_single_value("Global Defaults", "default_company")
	ca_sources = frappe.db.get_list(
		"Lead Source", ["name", "ais_report_label"],
		{"name": ["not in", _EXCLUDED_SOURCES], "neb_company": default_company},
	)

	ca_store_rows, ca_stores_grand = build_store_section(ca_sources, store_closings, date, _CA_STORES_ORDER)
	data.extend(ca_store_rows)

	data.append({"location": "Online"})
	ca_web_rows, ca_web_grand = build_website_section(ca_sources, date, _CA_WEB_ORDER)
	data.extend(ca_web_rows)

	append_region_totals(data, ca_stores_grand, ca_web_grand, "CAD")

	# ── USA section ──────────────────────────────────────────────────────────
	us_companies = frappe.db.get_list(
		"Company", filters={"country": "United States", "is_group": 0}, fields=["name"]
	)
	if us_companies:
		us_company_names = [c.name for c in us_companies]
		us_sources = frappe.db.get_all(
			"Lead Source", {"neb_company": ["in", us_company_names]}, ["name", "ais_report_label"]
		)
		if us_sources:
			us_store_rows, us_stores_grand = build_store_section(us_sources, store_closings, date, [])
			us_web_rows, us_web_grand = build_website_section(us_sources, date, [])

			if us_store_rows or us_web_rows:
				data.append({"location": "USA"})
				data.extend(us_store_rows)
				data.append({"location": "Online"})
				data.extend(us_web_rows)
				append_region_totals(data, us_stores_grand, us_web_grand, "USD")

	return get_columns(), data


# ── Columns ───────────────────────────────────────────────────────────────────

def get_columns():
	return [
		{"fieldname": "location",  "fieldtype": "Data",     "label": "Location",  "width": 200},
		{"fieldname": "user",      "fieldtype": "HTML",     "label": "User",      "width": 180},
		{"fieldname": "cash_sales","fieldtype": "Currency", "label": "Cash Sales","width": 120},
		{"fieldname": "expected",  "fieldtype": "Currency", "label": "Expected",  "width": 130},
		{"fieldname": "actual",    "fieldtype": "Currency", "label": "Actual",    "width": 130},
		{"fieldname": "difference","fieldtype": "Currency", "label": "Difference","width": 120},
		{"fieldname": "notes",     "fieldtype": "Data",     "label": "Note",      "width": 180},
		{"fieldname": "space",     "fieldtype": "Data",     "label": "",          "width": 60},
		{"fieldname": "total_mtd", "fieldtype": "Currency", "label": "CMA Sales", "width": 120},
		{"fieldname": "total_pmtd","fieldtype": "Currency", "label": "PYMA Sales","width": 120},
	]


# ── Section builders ──────────────────────────────────────────────────────────

def build_store_section(all_sources, store_closings, date, preferred_order):
	store_sources = [
		s for s in all_sources
		if s.name.split("-")[0].strip() != "Website"
		and s.ais_report_label
	]
	order_index = {name: i for i, name in enumerate(preferred_order)}
	store_sources = sorted(store_sources, key=lambda s: order_index.get(s.name, len(preferred_order)))

	rows = []
	grand = _empty_grand()

	for source in store_sources:
		closings = store_closings.get(source.name, [])
		store_label = source.ais_report_label
		store_level = get_store_level_data(source.name, date)

		closing_names = [c.name for c in closings]
		cash_sales = get_eod_cash_sales(closing_names)

		store_exp = store_act = store_diff = 0
		for c in closings:
			store_exp  += c.mop_total_expected  or 0
			store_act  += c.mop_total_actual     or 0
			store_diff += c.mop_total_difference or 0

		if not closings:
			rows.append({
				"location": store_label,
				**store_level,
			})

		elif len(closings) == 1:
			c = closings[0]
			rows.append({
				"location":  store_label,
				"user":      _user_link(c),
				"cash_sales":cash_sales,
				"expected":  c.mop_total_expected  or 0,
				"actual":    c.mop_total_actual     or 0,
				"difference":c.mop_total_difference or 0,
				"notes":     c.closing_notes        or "",
				**store_level,
			})

		else:
			for idx, c in enumerate(closings):
				rows.append({
					"location":  store_label if idx == 0 else "",
					"user":      _user_link(c),
					"cash_sales":get_eod_cash_sales([c.name]),
					"expected":  c.mop_total_expected  or 0,
					"actual":    c.mop_total_actual     or 0,
					"difference":c.mop_total_difference or 0,
					"notes":     c.closing_notes        or "",
				})
			rows.append({
				"location":  f"{store_label} — Total",
				"cash_sales":cash_sales,
				"expected":  store_exp,
				"actual":    store_act,
				"difference":store_diff,
				"bold":      1,
				**store_level,
			})

		grand["cash_sales"]  += cash_sales
		grand["expected"]    += store_exp
		grand["actual"]      += store_act
		grand["difference"]  += store_diff
		grand["total_mtd"]   += store_level["total_mtd"]
		grand["total_pmtd"]  += store_level["total_pmtd"]

	return rows, grand


def build_website_section(all_sources, date, preferred_order):
	web_sources = [
		s for s in all_sources
		if s.name.split("-")[0].strip() == "Website"
		and s.ais_report_label
	]
	order_index = {name: i for i, name in enumerate(preferred_order)}
	web_sources = sorted(web_sources, key=lambda s: order_index.get(s.name, len(preferred_order)))

	rows = []
	grand = _empty_grand()

	for source in web_sources:
		web_level = get_website_level_data(source.name, date)
		rows.append({"location": source.ais_report_label, **web_level})

		grand["total_mtd"]  += web_level["total_mtd"]
		grand["total_pmtd"] += web_level["total_pmtd"]

	return rows, grand


def append_region_totals(data, stores_grand, web_grand, currency):
	data.append({})
	data.append({
		"location":  "Stores — Total",
		"cash_sales":stores_grand["cash_sales"],
		"expected":  stores_grand["expected"],
		"actual":    stores_grand["actual"],
		"difference":stores_grand["difference"],
		"total_mtd": stores_grand["total_mtd"],
		"total_pmtd":stores_grand["total_pmtd"],
		"bold":      1,
	})
	data.append({
		"location":  "Websites — Total",
		"total_mtd": web_grand["total_mtd"],
		"total_pmtd":web_grand["total_pmtd"],
		"bold":      1,
	})
	data.append({
		"location":  f"{currency} Total",
		"cash_sales":stores_grand["cash_sales"],
		"expected":  stores_grand["expected"],
		"actual":    stores_grand["actual"],
		"difference":stores_grand["difference"],
		"total_mtd": stores_grand["total_mtd"] + web_grand["total_mtd"],
		"total_pmtd":stores_grand["total_pmtd"] + web_grand["total_pmtd"],
		"bold":      1,
	})


# ── Data fetchers ─────────────────────────────────────────────────────────────

def get_store_level_data(source_name, date):
	"""MTD and PMTD totals from submitted EOD Closings for the store."""
	selected_date = datetime.strptime(date, "%Y-%m-%d")

	mtd_start = selected_date.strftime("%Y-%m-01")
	total_mtd = _eod_closing_total(source_name, mtd_start, date)

	prev = selected_date + relativedelta(years=-1)
	pmtd_start = prev.strftime("%Y-%m-01")
	pmtd_end   = prev.strftime("%Y-%m-%d")
	total_pmtd = _eod_closing_total(source_name, pmtd_start, pmtd_end)

	return {"total_mtd": total_mtd, "total_pmtd": total_pmtd}


def get_website_level_data(source_name, date):
	selected_date = datetime.strptime(date, "%Y-%m-%d")

	sd = get_website_orders_sql(source_name, date, field="total_without_tax")
	daily_total = sd[0].total_without_tax if sd else 0

	mtd_start = selected_date.strftime("%Y-%m-01")
	sd_mtd = get_website_orders_sql(source_name, mtd_start, end_date=date, field="total_mtd")
	total_mtd = sd_mtd[0].total_mtd if sd_mtd else 0

	prev = selected_date + relativedelta(years=-1)
	pmtd_start = prev.strftime("%Y-%m-01")
	pmtd_end   = prev.strftime("%Y-%m-%d")
	sd_pmtd = get_website_orders_sql(source_name, pmtd_start, end_date=pmtd_end, field="total_pmtd")
	total_pmtd = sd_pmtd[0].total_pmtd if sd_pmtd else 0

	return {
		"expected":   daily_total,
		"total_mtd":  total_mtd,
		"total_pmtd": total_pmtd,
	}


def get_eod_cash_sales(closing_names):
	"""Sum of actual cash from EOD Payments child table for the given closings."""
	if not closing_names:
		return 0
	placeholders = ", ".join(["%s"] * len(closing_names))
	result = frappe.db.sql(f"""
		SELECT COALESCE(SUM(actual), 0) AS cash_total
		FROM `tabEOD Payments`
		WHERE parent IN ({placeholders})
		AND mode_of_payment = 'Cash'
	""", tuple(closing_names), as_dict=1)
	return result[0].cash_total if result else 0


def _eod_closing_total(source_name, start_date, end_date):
	"""Sum of mop_total_actual from submitted EOD Closings for a date range."""
	result = frappe.db.sql("""
		SELECT COALESCE(SUM(mop_total_actual), 0) AS total
		FROM `tabEnd of Day Closing`
		WHERE lead_source = %s
		AND closing_date BETWEEN %s AND %s
		AND docstatus = 1
	""", (source_name, start_date, end_date), as_dict=1)
	return result[0].total if result else 0


# ── Utilities ─────────────────────────────────────────────────────────────────

def _user_link(closing):
	safe_name = frappe.utils.escape_html(closing.user_name or closing.user or "")
	return f'<a href="/app/end-of-day-closing/{closing.name}" target="_blank">{safe_name}</a>'


def _empty_grand():
	return {
		"cash_sales":  0,
		"expected":    0,
		"actual":      0,
		"difference":  0,
		"total_mtd":   0,
		"total_pmtd":  0,
	}
