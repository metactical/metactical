# Copyright (c) 2024, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class EndofDayClosing(Document):
	pass

@frappe.whitelist()
def get_data(closing_date, user, pos_profile, source):
	mode_of_payments = {}
	invoices = []
	expected_cash = 0
	order_payments = []
	orders = []
	
	invoice_payments = frappe.db.sql("""
				SELECT
					SUM(payment_reference.allocated_amount) AS amount_paid,
					payment_entry.mode_of_payment, mop.type
				FROM
					`tabPayment Entry Reference` AS payment_reference
				LEFT JOIN
					`tabPayment Entry` AS payment_entry ON payment_reference.parent = payment_entry.name
				LEFT JOIN
					`tabSales Invoice` AS invoice ON invoice.name = payment_reference.reference_name
				LEFT JOIN
					`tabMode of Payment` AS mop ON mop.name = payment_entry.mode_of_payment
				WHERE
					payment_entry.posting_date = %(closing_date)s AND payment_entry.payment_type = 'Receive'
					AND payment_reference.reference_doctype = "Sales Invoice" AND invoice.pos_profile = %(pos_profile)s
				GROUP BY 
					payment_entry.mode_of_payment, type
				""", {"closing_date": closing_date, "pos_profile": pos_profile}, as_dict=1)
				
	pos_payments = frappe.db.sql("""
				SELECT
					SUM(payment.amount) AS amount_paid, 
					payment.mode_of_payment, mop.type
				FROM
					`tabSales Invoice Payment` AS payment
				LEFT JOIN
					`tabSales Invoice` AS invoice ON invoice.name = payment.parent
				LEFT JOIN
					`tabMode of Payment` AS mop ON mop.name = payment.mode_of_payment
				WHERE
					invoice.posting_date = %(closing_date)s AND invoice.pos_profile = %(pos_profile)s
				GROUP BY
					payment.mode_of_payment, type
				""", {"closing_date": closing_date, "pos_profile": pos_profile}, as_dict=1)
				
	if source is not None and source != "":		
		order_payments = frappe.db.sql("""
					SELECT
						SUM(payment_reference.allocated_amount) AS amount_paid,
						payment_entry.mode_of_payment, mop.type
					FROM
						`tabPayment Entry Reference` AS payment_reference
					LEFT JOIN
						`tabPayment Entry` AS payment_entry ON payment_reference.parent = payment_entry.name
					LEFT JOIN
						`tabSales Order` AS sorder ON sorder.name = payment_reference.reference_name
					LEFT JOIN
						`tabMode of Payment` AS mop ON mop.name = payment_entry.mode_of_payment
					WHERE
						payment_entry.posting_date = %(closing_date)s AND payment_entry.payment_type = 'Receive'
						AND payment_reference.reference_doctype = "Sales Order" AND sorder.source = %(source)s
					GROUP BY 
						payment_entry.mode_of_payment, type
					""", {"closing_date": closing_date, "source": source}, as_dict=1)
	
	for payment in invoice_payments:
		mode_of_payments[payment.mode_of_payment] = mode_of_payments.get(payment.mode_of_payment, 0) + payment.amount_paid
		if payment.type == "Cash":
			expected_cash += payment.amount_paid
			
	for payment in order_payments:
		mode_of_payments[payment.mode_of_payment] = mode_of_payments.get(payment.mode_of_payment, 0) + payment.amount_paid
		if payment.type == "Cash":
			expected_cash += payment.amount_paid
	
	for payment in pos_payments:
		mode_of_payments[payment.mode_of_payment] = mode_of_payments.get(payment.mode_of_payment, 0) + payment.amount_paid
		if payment.type == "Cash":
			expected_cash += payment.amount_paid
				
	invoices = frappe.db.sql("""
				SELECT
					payment_reference.reference_doctype, payment_reference.reference_name, 
					SUM(payment_reference.allocated_amount) AS amount_paid,
					invoice.outstanding_amount AS owing
				FROM
					`tabPayment Entry Reference` AS payment_reference
				LEFT JOIN
					`tabPayment Entry` AS payment_entry ON payment_reference.parent = payment_entry.name
				LEFT JOIN
					`tabSales Invoice` AS invoice ON invoice.name = payment_reference.reference_name
				WHERE
					payment_entry.posting_date = %(closing_date)s AND payment_entry.payment_type = 'Receive'
					AND payment_reference.reference_doctype = "Sales Invoice" AND invoice.pos_profile = %(pos_profile)s
				GROUP BY
					reference_doctype, reference_name, owing
				""", {"closing_date": closing_date, "pos_profile": pos_profile}, as_dict=1)
				
	pos_invoices = frappe.db.sql("""
				SELECT
					"Sales Invoice" AS reference_doctype, invoice.name AS reference_name,
					invoice.outstanding_amount AS owing, 
					invoice.paid_amount AS amount_paid
				FROM
					`tabSales Invoice Payment` AS payment
				LEFT JOIN
					`tabSales Invoice` AS invoice ON invoice.name = payment.parent
				WHERE
					invoice.posting_date = %(closing_date)s AND invoice.pos_profile = %(pos_profile)s
				GROUP BY
					reference_doctype, reference_name, owing, amount_paid
				""", {"closing_date": closing_date, "pos_profile": pos_profile}, as_dict=1)
				
	if source is not None and source != "":
		orders = frappe.db.sql("""
				SELECT
					payment_reference.reference_doctype, payment_reference.reference_name, 
					SUM(payment_reference.allocated_amount) AS amount_paid,
					(sorder.grand_total - sorder.advance_paid) AS owing
				FROM
					`tabPayment Entry Reference` AS payment_reference
				LEFT JOIN
					`tabPayment Entry` AS payment_entry ON payment_reference.parent = payment_entry.name
				LEFT JOIN
					`tabSales Order` AS sorder ON sorder.name = payment_reference.reference_name
				WHERE
					payment_entry.posting_date = %(closing_date)s AND payment_entry.payment_type = 'Receive'
					AND payment_reference.reference_doctype = "Sales Order" AND sorder.source = %(source)s
				GROUP BY
					reference_doctype, reference_name, owing
				""", {"closing_date": closing_date, "source": source}, as_dict=1)
				
	invoices = invoices + pos_invoices + orders
	
	return {"payments": mode_of_payments, "invoices": invoices, "expected_cash": expected_cash}
				
	
