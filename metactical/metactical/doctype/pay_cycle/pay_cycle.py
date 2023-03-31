# Copyright (c) 2023, Metactical and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document

class PayCycle(Document):
	def before_insert(self):
		self.naming_field = f'Cycle {self.user}-{self.from_date}-{self.to_date}'

	def before_save(self):
		self.update_hours()

	def update_hours(self):
		total_pay_cycle_hours = 0.0
		
		for hours in self.days:
			total_pay_cycle_hours += hours.hours_worked

		self.total_hours_worked = total_pay_cycle_hours
