# Copyright (c) 2026, Storebuilder Commerce Inc and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import add_days, date_diff, getdate


def execute(filters=None):
	filters = frappe._dict(filters or {})

	columns = get_columns()
	data = get_data(filters)
	data = append_summary_rows(data)

	return columns, data


def get_columns():
	return [
		{"label": _("Item Code"), "fieldname": "item_code", "fieldtype": "Data", "width": 150},
		{"label": _("Customer Email"), "fieldname": "customer_email", "fieldtype": "Data", "width": 200},
		{"label": _("Lead Source"), "fieldname": "lead_source", "fieldtype": "Data", "width": 140},
		{"label": _("Email Sent At"), "fieldname": "sent_at", "fieldtype": "Datetime", "width": 160},
		{"label": _("Email Status"), "fieldname": "email_status", "fieldtype": "Data", "width": 110},
		{"label": _("Sales Order"), "fieldname": "sales_order", "fieldtype": "Data", "width": 140},
		{"label": _("Order Date"), "fieldname": "order_date", "fieldtype": "Date", "width": 110},
		{"label": _("Days to Convert"), "fieldname": "days_to_convert", "fieldtype": "Int", "width": 120},
		{"label": _("Converted"), "fieldname": "converted", "fieldtype": "Data", "width": 100},
	]


def get_data(filters):
	rows = []
	for log in get_email_logs(filters):
		so = find_matching_sales_order(log, filters.get("conversion_window"))

		if so:
			order_date = so.transaction_date
			days_to_convert = date_diff(so.transaction_date, getdate(log.sent_at))
		else:
			order_date = None
			days_to_convert = None

		rows.append(frappe._dict({
			"item_code": log.item_code,
			"customer_email": log.customer_email,
			"lead_source": log.lead_source,
			"sent_at": log.sent_at,
			"email_status": log.delivery_status,
			"sales_order": so.name if so else None,
			"order_date": order_date,
			"days_to_convert": days_to_convert,
			"converted": "Yes" if so else "No",
		}))

	if filters.get("converted") and filters.converted != "All":
		rows = [r for r in rows if r.converted == filters.converted]

	return rows


def get_email_logs(filters):
	"""Return the sent Restock Email Logs in scope, newest first.

	Base population is emails that were actually sent (`status` = "Sent"). The
	`delivery_status` field (Delivered/Opened/Clicked, set later by the mail
	service) is shown as the Email Status column and can be filtered optionally.
	"""
	log_filters = [["status", "=", "Sent"]]

	if filters.get("from_date"):
		log_filters.append(["sent_at", ">=", filters.from_date])
	if filters.get("to_date"):
		log_filters.append(["sent_at", "<", add_days(getdate(filters.to_date), 1)])
	if filters.get("lead_source"):
		log_filters.append(["lead_source", "=", filters.lead_source])
	if filters.get("item_code"):
		log_filters.append(["item_code", "=", filters.item_code])
	if filters.get("email_status"):
		log_filters.append(["delivery_status", "=", filters.email_status])

	return frappe.get_all(
		"Restock Email Log",
		filters=log_filters,
		fields=["name", "item_code", "customer_email", "lead_source", "sent_at", "delivery_status"],
		order_by="sent_at desc",
	)


def find_matching_sales_order(log, conversion_window=None):
	"""Earliest submitted Sales Order that contains the item, was created on/after the
	email (and optionally within the conversion window), and whose email matches the log.
	Returns the Sales Order dict (name, transaction_date) or None."""
	# Sales Orders that contain this item in a line.
	candidate_names = frappe.get_all(
		"Sales Order Item",
		filters={"item_code": log.item_code, "docstatus": 1},
		pluck="parent",
	)
	if not candidate_names:
		return None

	sent_date = getdate(log.sent_at)
	so_filters = [
		["name", "in", list(set(candidate_names))],
		["docstatus", "=", 1],
		["transaction_date", ">=", sent_date],
	]
	if conversion_window:
		cutoff = add_days(sent_date, int(conversion_window))
		so_filters.append(["transaction_date", "<=", cutoff])

	candidates = frappe.get_all(
		"Sales Order",
		filters=so_filters,
		fields=[
			"name", "transaction_date", "contact_email",
			"customer_address", "shipping_address_name", "contact_person",
		],
		order_by="transaction_date asc, creation asc",
	)

	# Earliest matching order (by order date) whose email matches the log.
	for so in candidates:
		if log.customer_email in sales_order_emails(so):
			return so
	return None


def sales_order_emails(so):
	"""All emails associated with a Sales Order: the header contact_email, the billing
	and shipping address emails, and the linked contact's email."""
	emails = {so.contact_email}
	if so.customer_address:
		emails.add(frappe.db.get_value("Address", so.customer_address, "email_id"))
	if so.shipping_address_name:
		emails.add(frappe.db.get_value("Address", so.shipping_address_name, "email_id"))
	if so.contact_person:
		emails.add(frappe.db.get_value("Contact", so.contact_person, "email_id"))
	return {e for e in emails if e}


def append_summary_rows(data):
	total = len(data)
	converted_rows = [r for r in data if r.get("converted") == "Yes"]
	total_converted = len(converted_rows)

	conversion_rate = round((total_converted / total) * 100, 2) if total else 0.0

	convert_days = [r.get("days_to_convert") for r in converted_rows if r.get("days_to_convert") is not None]
	avg_days = round(sum(convert_days) / len(convert_days), 2) if convert_days else None

	data.append({})
	data.append({"item_code": _("Total Emails"), "days_to_convert": None, "converted": total})
	data.append({"item_code": _("Total Converted"), "days_to_convert": None, "converted": total_converted})
	data.append({"item_code": _("Conversion Rate %"), "days_to_convert": None, "converted": conversion_rate})
	data.append({"item_code": _("Avg Days to Convert"), "days_to_convert": None, "converted": avg_days})

	return data
