# Copyright (c) 2023, Metactical and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from datetime import datetime
from metactical.api.clockin import insert_in_employee_checkin


class ClockinLog(Document):
	def after_insert(self):
		insert_in_employee_checkin(self)
		
	def on_update(self):
		self.update_user_pay_cycle_record()
	
	def before_save(self):
		# Validate total hours worked for clockin log
		if self.has_clocked_out:
			self.total_hours = time_difference(self.from_time, self.to_time)
			self.insert_out_employee_checkin()
	
	def update_user_pay_cycle_record(self):
		clockin_logs = frappe.get_all("Clockin Log", filters={
			"user": self.user,
			"date": self.date,
			"has_clocked_out": 1,
			"name": ("!=", self.name)
		}, fields=['total_hours'])

		total_hours_worked = self.total_hours

		for clockin_log in clockin_logs:
			total_hours_worked += clockin_log.total_hours

		work_day = frappe.db.exists("Pay Cycle Log", {
			"owner": self.user,
			"date": self.date
		})

		#Get parent field for work day
		parent_field = frappe.db.get_value("Pay Cycle Log", work_day, "parent")

		#Update work day hours
		frappe.db.set_value("Pay Cycle Log", work_day, "hours_worked", total_hours_worked)

		#Calculate total hours in pay cycle
		pay_cycle_record = frappe.get_doc("Pay Cycle", parent_field)
		pay_cycle_record.update_hours()
		pay_cycle_record.save()
		
	def insert_out_employee_checkin(self):
		employee_exists = frappe.db.exists("Employee", {"user_id": self.user})

		if employee_exists:
			if self.has_clocked_out:
				if not self.out_employee_checkin_record:
					#Create employee out checkin record
					out_employee_checkin = frappe.get_doc({
						"doctype": "Employee Checkin",
						"log_type": "OUT",
						"employee": employee_exists,
						"time": self.to_time
					})

					out_employee_checkin.insert(ignore_permissions=True)

					#Link record
					self.out_employee_checkin_record = out_employee_checkin.name

				else:
					out_employee_checkin_record = frappe.get_doc("Employee Checkin", self.out_employee_checkin_record)
					out_employee_checkin_record.time = self.to_time
					out_employee_checkin_record.save()

					in_employee_checkin_record = frappe.get_doc("Employee Checkin", self.in_employee_checkin_record)
					in_employee_checkin_record.time = self.from_time
					in_employee_checkin_record.save()

		else:
			frappe.throw("Employee record not found")

def time_difference(time1, time2):
	# convert times to datetime objects
	if type(time1) is str:
		time1 = datetime.strptime(time1, "%Y-%m-%d %H:%M:%S")
	
	if type(time2) is str:
		time2 = datetime.strptime(time2, "%Y-%m-%d %H:%M:%S")
	
	# calculate the difference between times
	time_diff = abs(time1 - time2)
	
	# convert difference to hours
	time_diff_hours = time_diff.total_seconds() / 3600
	
	return time_diff_hours
