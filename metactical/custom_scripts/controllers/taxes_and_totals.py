import frappe
from erpnext.controllers.taxes_and_totals import calculate_taxes_and_totals

class custom_calculate_taxes_and_totals(calculate_taxes_and_totals):
	def set_total_amount_to_default_mop(self, total_amount_to_pay):
		total_paid_amount = 0
		for payment in self.doc.get("payments"):
			total_paid_amount += (
				payment.amount if self.doc.party_account_currency == self.doc.currency else payment.base_amount
			)

		pending_amount = total_amount_to_pay - total_paid_amount
		
		# Metactical Customization: If it's a return invoice, set the paid amount equal to the grand total
		if self.doc.get("is_return") and pending_amount > 0:
			default_mode_of_payment = frappe.db.get_value(
				"POS Payment Method",
				{"parent": self.doc.pos_profile, "default": 1},
				["mode_of_payment"],
				as_dict=1,
			)

			if default_mode_of_payment:
				self.doc.payments = []
				self.doc.append(
					"payments",
					{
						"mode_of_payment": default_mode_of_payment.mode_of_payment,
						"amount": self.doc.get("grand_total"),
						"default": 1,
					},
				)
		elif pending_amount > 0:
			default_mode_of_payment = frappe.db.get_value(
				"POS Payment Method",
				{"parent": self.doc.pos_profile, "default": 1},
				["mode_of_payment"],
				as_dict=1,
			)

			if default_mode_of_payment:
				self.doc.payments = []
				self.doc.append(
					"payments",
					{
						"mode_of_payment": default_mode_of_payment.mode_of_payment,
						"amount": pending_amount,
						"default": 1,
					},
				)
