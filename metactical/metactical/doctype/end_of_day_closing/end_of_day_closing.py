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
		
	invoices = frappe.db.sql("""
				SELECT
					payment_reference.reference_doctype, payment_reference.reference_name, 
					payment_reference.allocated_amount AS amount_paid,
					invoice.outstanding_amount AS owing, payment_entry.mode_of_payment
				FROM
					`tabPayment Entry Reference` AS payment_reference
				LEFT JOIN
					`tabPayment Entry` AS payment_entry ON payment_reference.parent = payment_entry.name
				LEFT JOIN
					`tabSales Invoice` AS invoice ON invoice.name = payment_reference.reference_name
				WHERE
					payment_entry.posting_date = %(closing_date)s AND payment_entry.payment_type = 'Receive'
					AND payment_reference.reference_doctype = "Sales Invoice" AND invoice.pos_profile = %(pos_profile)s
				""", {"closing_date": closing_date, "pos_profile": pos_profile}, as_dict=1)
				
	pos_invoices = frappe.db.sql("""
				SELECT
					"Sales Invoice" AS reference_doctype, invoice.name AS reference_name,
					invoice.outstanding_amount AS owing, 
					invoice.paid_amount AS amount_paid, payment.mode_of_payment,
					invoice.change_amount,
					change_account.account_type AS change_account_type
				FROM
					`tabSales Invoice Payment` AS payment
				LEFT JOIN
					`tabSales Invoice` AS invoice ON invoice.name = payment.parent
				LEFT JOIN
					`tabAccount` AS change_account ON change_account.name = invoice.account_for_change_amount
				WHERE
					invoice.posting_date = %(closing_date)s AND invoice.pos_profile = %(pos_profile)s
				""", {"closing_date": closing_date, "pos_profile": pos_profile}, as_dict=1)
				
	if source is not None and source != "":
		orders = frappe.db.sql("""
				SELECT
					payment_reference.reference_doctype, payment_reference.reference_name, 
					payment_reference.allocated_amount AS amount_paid,
					(sorder.grand_total - sorder.advance_paid) AS owing, payment_entry.mode_of_payment
				FROM
					`tabPayment Entry Reference` AS payment_reference
				LEFT JOIN
					`tabPayment Entry` AS payment_entry ON payment_reference.parent = payment_entry.name
				LEFT JOIN
					`tabSales Order` AS sorder ON sorder.name = payment_reference.reference_name
				WHERE
					payment_entry.posting_date = %(closing_date)s AND payment_entry.payment_type = 'Receive'
					AND payment_reference.reference_doctype = "Sales Order" AND sorder.source = %(source)s
				""", {"closing_date": closing_date, "source": source}, as_dict=1)
	
	for payment in invoices:
		mode_of_payments[payment.mode_of_payment] = mode_of_payments.get(payment.mode_of_payment, 0) + payment.amount_paid
		if payment.mode_of_payment == "Cash":
			expected_cash += payment.amount_paid
			
	for payment in orders:
		mode_of_payments[payment.mode_of_payment] = mode_of_payments.get(payment.mode_of_payment, 0) + payment.amount_paid
		if payment.mode_of_payment == "Cash":
			expected_cash += payment.amount_paid
	
	for payment in pos_invoices:
		# if there is chenge amount, remove it from cash
		if payment.change_account_type == "Cash" and payment.mode_of_payment == "Cash":
			payment.amount_paid -= payment.change_amount

		mode_of_payments[payment.mode_of_payment] = mode_of_payments.get(payment.mode_of_payment, 0) + payment.amount_paid
		if payment.mode_of_payment == "Cash":
			expected_cash += payment.amount_paid

	invoices = invoices + pos_invoices + orders
	
	return {"payments": mode_of_payments, "invoices": invoices, "expected_cash": expected_cash}
				
	
