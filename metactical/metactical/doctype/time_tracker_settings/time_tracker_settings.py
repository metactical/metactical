# Copyright (c) 2023, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from datetime import datetime, timedelta

class TimeTrackerSettings(Document):
	def validate(self):
		self.generate_pay_cycles()

		for i, item in enumerate(sorted(self.pay_cycles, key=lambda item: item.from_date, reverse=True), start=1):
			item.idx = i

	def generate_pay_cycles(self):
		start_date = self.start_date #datetime(2023, 1, 30) # specify your start date
		
		one_year = timedelta(days=365)
		start_date_object = datetime.strptime(self.start_date, '%Y-%m-%d').date()
		end_date = start_date_object + one_year #datetime(2024, 1, 30) # specify your end date
		delta = timedelta(days=13)

		use_delta_one = False

		date_array = []

		while start_date_object <= end_date:
			date_array.append(start_date_object.strftime('%Y-%m-%d'))
			
			if not use_delta_one:
				start_date_object += delta
				
			else:
				start_date_object += timedelta(days=1)
			
			use_delta_one = not use_delta_one

		from_dates = date_array[::2]
		to_dates = date_array[1::2]
		date_pairs = []

		for i in range(len(to_dates)):
			date_pair = []
			date_pair.append(from_dates[i])
			date_pair.append(to_dates[i])
			date_pairs.append(date_pair)
   
		#Clear child table
		self.pay_cycles = []

		for d in range(len(date_pairs)):
			frappe.errprint(date_pairs[d][0])
			frappe.errprint(date_pairs[d][1])

			row = self.append("pay_cycles", {
				"from_date": date_pairs[d][0],
				"to_date": date_pairs[d][1]
			})

			row.insert()