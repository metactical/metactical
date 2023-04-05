# Copyright (c) 2023, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
from operator import itemgetter

def execute(filters=None):
	columns, data = [], []
	columns = get_columns(filters)
	data = get_data(filters)
	return columns, data
	
def get_data(filters):
	data = []
	#Get company abbreviation
	abbr = frappe.db.get_value("Company", filters.get("company"), "abbr")
	payment_entries = frappe.db.sql("""
							SELECT
								invoice.posting_date AS invoice_date, payment.posting_date AS pe_posting_date,
								payment.payment_type, invoice.name AS invoice_no, payment.mode_of_payment,
								pe_ref.allocated_amount AS mop_breakdown, invoice.source AS lead_source,
								invoice.status AS invoice_status, address.state AS province, 
								address.country, invoice.total AS sub_total, SUM(gst_hst.tax_amount) AS gst_amount,
								SUM(pst.tax_amount) AS pst_amount, SUM(qst.tax_amount) AS qst_amount,
								invoice.grand_total AS final_amount, invoice.currency, pe_ref.name
							FROM
								`tabPayment Entry Reference` AS pe_ref
							LEFT JOIN
								`tabSales Invoice` AS invoice ON pe_ref.reference_name = invoice.name
							LEFT JOIN
								`tabPayment Entry` AS payment ON payment.name = pe_ref.parent
							LEFT JOIN
								`tabAddress` AS address ON invoice.customer_address = address.name
							LEFT JOIN
								`tabSales Taxes and Charges` AS gst_hst ON gst_hst.parenttype = 'Sales Invoice' AND 
									gst_hst.parent = invoice.name AND (gst_hst.account_head = 'HST - {abbr}' OR 
									gst_hst.account_head = 'GST - {abbr}')
							LEFT JOIN
								`tabSales Taxes and Charges` AS pst ON pst.parenttype = 'Sales Invoice' AND 
									pst.parent = invoice.name AND pst.account_head = 'PST - {abbr}'
							LEFT JOIN
								`tabSales Taxes and Charges` AS qst ON qst.parenttype = 'Sales Invoice' AND 
									qst.parent = invoice.name AND qst.account_head = 'QST - {abbr}'
							WHERE
								pe_ref.reference_doctype = 'Sales Invoice' AND invoice.docstatus = 1 AND
								payment.posting_date BETWEEN '{start_date}' AND '{end_date}'
							GROUP BY
								invoice_date, pe_posting_date, payment.payment_type, invoice_no, payment.mode_of_payment,
								mop_breakdown, lead_source, invoice_status, province, 
								address.country, sub_total, final_amount, invoice.currency, pe_ref.name
							ORDER BY
								invoice_no
					""".format(abbr = abbr, start_date = filters.get("start_date"), end_date = filters.get("end_date")), as_dict=1)
					
	pos_invoices = frappe.db.sql("""
							SELECT
								invoice.posting_date AS invoice_date, invoice.posting_date AS pe_posting_date,
								'Receive' AS payment_type, invoice.name AS invoice_no, pe_ref.mode_of_payment,
								pe_ref.amount AS mop_breakdown, invoice.source AS lead_source,
								invoice.status AS invoice_status, address.state AS province, 
								address.country, invoice.total AS sub_total, SUM(gst_hst.tax_amount) AS gst_amount,
								SUM(pst.tax_amount) AS pst_amount, SUM(qst.tax_amount) AS qst_amount,
								invoice.grand_total AS final_amount, invoice.currency, pe_ref.name
							FROM
								`tabSales Invoice Payment` AS pe_ref
							LEFT JOIN
								`tabSales Invoice` AS invoice ON pe_ref.parent = invoice.name
							LEFT JOIN
								`tabAddress` AS address ON invoice.customer_address = address.name
							LEFT JOIN
								`tabSales Taxes and Charges` AS gst_hst ON gst_hst.parenttype = 'Sales Invoice' AND 
									gst_hst.parent = invoice.name AND (gst_hst.account_head = 'HST - {abbr}' OR 
									gst_hst.account_head = 'GST - {abbr}')
							LEFT JOIN
								`tabSales Taxes and Charges` AS pst ON pst.parenttype = 'Sales Invoice' AND 
									pst.parent = invoice.name AND pst.account_head = 'PST - {abbr}'
							LEFT JOIN
								`tabSales Taxes and Charges` AS qst ON qst.parenttype = 'Sales Invoice' AND 
									qst.parent = invoice.name AND qst.account_head = 'QST - {abbr}'
							WHERE
								invoice.docstatus = 1 AND pe_ref.parenttype = 'Sales Invoice' AND 
								invoice.posting_date BETWEEN '{start_date}' AND '{end_date}'
							GROUP BY
								invoice_date, pe_posting_date, payment_type, invoice_no, pe_ref.mode_of_payment,
								mop_breakdown, lead_source, invoice_status, province, 
								address.country, sub_total, final_amount, invoice.currency, pe_ref.name
							ORDER BY
								invoice_no
					""".format(abbr = abbr, start_date = filters.get("start_date"), end_date = filters.get("end_date")), as_dict=1)
	data = payment_entries + pos_invoices
	data = sorted(data, key=itemgetter("invoice_no"))
	previous_invoice = ""
	for row in data:
		# If the invoice is the same as the previous one, it means it had mulitple
		# payments, so remove product subtotals and taxes information from the 
		# second row
		if row.invoice_no != previous_invoice:
			previous_invoice = row.invoice_no
		else:
			row["sub_total"] = ""
			row["final_amount"] = ""
			row["gst_amount"] = ""
			row["pst_amount"] = ""
			row["qst_amount"] = ""
			row["invoice_date"] = ""
	return data
	
def get_columns(filters):
	columns = [
		{
			"label": "SalesInvoiceDate",
			"fieldname": "invoice_date",
			"fieldtype": "Date",
			"width": "130"
		},
		{
			"label": "PaymentEntryPostingDate",
			"fieldname": "pe_posting_date",
			"fieldtype": "Date",
			"width": "130"
		},
		{
			"label": "Payment Type",
			"fieldname": "payment_type",
			"fieldtype": "Data",
			"width": "130"
		},
		{
			"label": "SaleInvoiceNumber",
			"fieldname": "invoice_no",
			"fieldtype": "Link",
			"options": "Sales Invoice",
			"width": "130"
		},
		{
			"label": "Mode of Payment",
			"fieldname": "mode_of_payment",
			"fieldtype": "Link",
			"options": "Mode of Payment",
			"width": "130"
		},
		{
			"label": "ModeOfPaymentBreakdown",
			"fieldname": "mop_breakdown",
			"fieldtype": "Currency",
			"width": "130"
		},
		{
			"label": "LeadSource",
			"fieldname": "lead_source",
			"fieldtype": "Link",
			"options": "Lead Source",
			"width": "130"
		},
		{
			"label": "Status",
			"fieldname": "invoice_status",
			"fieldtype": "Data",
			"width": "130"
		},
		{
			"label": "Province/State",
			"fieldname": "province",
			"fieldtype": "Data",
			"width": "130"
		},
		{
			"label": "Country",
			"fieldname": "country",
			"fieldtype": "Data",
			"width": "130"
		},
		{
			"label": "ProductSubTotal",
			"fieldname": "sub_total",
			"fieldtype": "Currency",
			"width": "130"
		},
		{
			"label": "GST/HST",
			"fieldname": "gst_amount",
			"fieldtype": "Currency",
			"width": "130"
		},
		{
			"label": "PST",
			"fieldname": "pst_amount",
			"fieldtype": "Currency",
			"width": "130"
		},
		{
			"label": "QST",
			"fieldname": "qst_amount",
			"fieldtype": "Currency",
			"width": "130"
		},
		{
			"label": "Final Amount",
			"fieldname": "final_amount",
			"fieldtype": "Currency",
			"width": "130"
		},
		{
			"label": "Currency",
			"fieldname": "currency",
			"fieldtype": "Link",
			"options": "Currency",
			"width": "130"
		}
	]
	return columns
