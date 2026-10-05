# Copyright (c) 2023, Metactical and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, get_datetime, getdate

from metactical.api.clockin import insert_in_employee_checkin
from metactical.time_tracker.core import hours_between


class ClockinLog(Document):
	def validate(self):
		if self.has_clocked_out and not self.to_time:
			frappe.throw(_("A clocked-out entry needs a To Time."))
		if self.to_time:
			hours = hours_between(self.from_time, self.to_time)
			if hours < 0:
				frappe.throw(_("To Time cannot be before From Time."))
			self.total_hours = hours
		if not self.has_clocked_out:
			clash = frappe.db.exists(
				"Clockin Log", {"user": self.user, "has_clocked_out": 0, "name": ("!=", self.name or "")}
			)
			if clash:
				frappe.throw(_("{0} is already clocked in ({1}).").format(self.user, clash))

	def after_insert(self):
		insert_in_employee_checkin(self)

	def before_save(self):
		if self.has_clocked_out:
			self.insert_out_employee_checkin()

	def on_update(self):
		sync_pay_cycle_day(self.user, self.date)
		before = self.get_doc_before_save()
		if before and getdate(before.date) != getdate(self.date):
			sync_pay_cycle_day(self.user, before.date)

	def on_trash(self):
		# Hours leave the day total once the entry is gone.
		frappe.db.after_commit.add(lambda: sync_pay_cycle_day(self.user, self.date))

	def insert_out_employee_checkin(self):
		employee = frappe.db.exists("Employee", {"user_id": self.user})
		if not employee:
			frappe.throw(_("Employee record not found"))

		if not self.out_employee_checkin_record:
			out = frappe.get_doc(
				{"doctype": "Employee Checkin", "log_type": "OUT", "employee": employee, "time": self.to_time}
			)
			out.insert(ignore_permissions=True)
			self.out_employee_checkin_record = out.name
		else:
			# Corrections move both punches so Attendance sees the approved times.
			for field, value in (
				("out_employee_checkin_record", self.to_time),
				("in_employee_checkin_record", self.from_time),
			):
				name = self.get(field)
				if name and frappe.db.exists("Employee Checkin", name):
					frappe.db.set_value("Employee Checkin", name, "time", value)


def sync_pay_cycle_day(user, day):
	"""Make the user's Pay Cycle show the right hours for `day`, creating the cycle if needed.

	The new Time Clock reads hours straight from Clockin Log; this keeps the older Pay Cycle
	documents and anything reporting on them in step.
	"""
	day = getdate(day)
	cycle = frappe.db.get_value(
		"Pay Cycle Record", {"from_date": ("<=", day), "to_date": (">=", day)}, ["from_date", "to_date"], as_dict=True
	)
	if not cycle:
		return

	name = frappe.db.get_value("Pay Cycle", {"user": user, "from_date": cycle.from_date, "to_date": cycle.to_date})
	if name:
		doc = frappe.get_doc("Pay Cycle", name)
	else:
		doc = frappe.get_doc(
			{"doctype": "Pay Cycle", "user": user, "from_date": cycle.from_date, "to_date": cycle.to_date}
		)

	existing = {getdate(r.date) for r in doc.days}
	d, end = getdate(cycle.from_date), getdate(cycle.to_date)
	while d <= end:  # bounded by the cycle's own end date
		if d not in existing:
			doc.append("days", {"date": d})
		d = add_days(d, 1)

	hours = frappe.db.sql(
		"select coalesce(sum(total_hours), 0) from `tabClockin Log` where user=%s and date=%s and has_clocked_out=1",
		(user, day),
	)[0][0]
	for row in doc.days:
		if getdate(row.date) == day:
			row.hours_worked = hours
	doc.save(ignore_permissions=True)
