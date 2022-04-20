# Copyright (c) 2013, Techlift Technologies and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from datetime import datetime, timedelta

def execute(filters=None):
	columns, data = [], []
	columns = get_columns(filters)
	employees = get_employees()
	checkins = get_checkins(employees, filters)
	for employee in employees:
		total = 0.00
		regular = 0.00
		other = 0.00
		next_logtype = 'IN'
		checkintime = None
		fieldname = ''
		# Do a checkin pair check. For every checkin there must be accompanying checkout.
		# If a checkin followed by another checkin thene the previous checkin is ignored.
		# If acheckout followed by another checkout then the second checkout is ignored
		for checkin in checkins:
			if checkin.employee == employee.name and checkin.log_type == next_logtype:
				if next_logtype == 'OUT':
					time = employee.get(fieldname, 0)
					timediff = (checkin.time - checkintime).total_seconds() / 3600
					current_time = time + timediff
					total = total + timediff
					employee.update({
						fieldname: round(current_time, 2)
					})
					next_logtype = 'IN'
				elif next_logtype == 'IN':
					fieldname = datetime.strftime(checkin.time, "%Y-%m-%d")
					checkintime = checkin.time
					next_logtype = 'OUT'
			elif checkin.employee == employee.name and checkin.log_type != next_logtype:
				if next_logtype == 'OUT':
					fieldname = datetime.strftime(checkin.time, "%Y-%m-%d")
					checkintime = checkin.time
					next_logtype = 'OUT'
					
		'''attendances = get_attendances(employees, filters)
		for employee in employees:
			total = 0.00
			regular = 0.00
			other = 0.00
			for attendance in attendances:
				if attendance.employee == employee.name and attendance.get('out_time') and attendance.get('in_time'):
					timediff = (attendance.out_time - attendance.in_time).seconds / 3600
					fieldname = datetime.strftime(attendance.attendance_date, "%Y-%m-%d")
					total = total + timediff
					employee.update({
						fieldname: round(timediff, 2)
					})'''
		
		if employee.get('isot') and employee.isot == 'Yes':
			regular = total
		elif employee.get('isot') and employee.isot == 'No':
			if total > 80:
				regular = 80
				other = total - 80
			else:
				regular = total
				
		if employee.get('isstudent') and employee.isstudent == 'Yes':
			if total > 20:
				regular = 20
				other = total - 20
			else:
				regular = total
		employee.update({
			"total": round(total, 2),
			"regular": round(regular, 2),
			"other": round(other, 2)
		})
		data.append(employee)
				
	return columns, data
	
def get_columns(filters):
	columns = [
		{
			"fieldtype": "Link",
			"fieldname": "branch",
			"label": "Branch",
			"options": "Branch",
			"width": 100
		},
		{
			"fieldtype": "Data",
			"fieldname": "akno",
			"label": "AKNo",
			"width": 100
		},
		{
			"fieldtype": "Data",
			"fieldname": "employee_name",
			"label": "Name",
			"width": 150
		},
		{
			"fieldtype": "Select",
			"fieldname": "isot",
			"label": "IsOT",
			"options": "Yes/nNo",
			"width": 100
		},
		{
			"fieldtype": "Select",
			"fieldname": "isstudent",
			"label": "IsStudent",
			"options": "Yes/nNo",
			"width": 100
		},		
		{
			"fieldtype": "Date",
			"fieldname": "sin_expiry",
			"label": "SIN Expiry",
			"width": 100
		},	
		{
			"fieldtype": "Select",
			"fieldname": "is_salary",
			"label": "IsSalary",
			"options": "Yes/nNo",
			"width": 100
		},
		{
			"fieldtype": "Data",
			"fieldname": "adpno",
			"label": "ADP No",
			"width": 100
		}
	]
	
	payment_cycle = frappe.get_doc("Payment Cycle", filters.get("payment_cycle"))
	start_date = payment_cycle.start_date
	end_date = payment_cycle.end_date
	diff = abs((end_date-start_date).days) + 1
	current_date = start_date
	for x in range(diff):
		columns.append({
			"fieldtype": "Float",
			"label": datetime.strftime(current_date, "%a (%d-%b-%Y)"),
			"width": 100,
			"precision": 2,
			"fieldname": datetime.strftime(current_date, "%Y-%m-%d")
		})
		current_date = current_date + timedelta(days=1)
	extra_fields = [
		{
			"fieldtype": "Float",
			"fieldname": "total",
			"label": "Total",
			"precision": 2,
			"width": 100
		},
		{
			"fieldtype": "Float",
			"fieldname": "regular",
			"label": "Regular",
			"precision": 2,
			"width": 100
		},
		{
			"fieldtype": "Float",
			"fieldname": "other",
			"label": "Other",
			"precision": 2,
			"width": 100
		},
		{
			"fieldtype": "Data",
			"fieldname": "mobile",
			"label": "Mobile",
			"width": 100
		},
		{
			"fieldtype": "Data",
			"fieldname": "personal_email",
			"label": "Personal Email",
			"width": 150
		}
	]
	columns.extend(extra_fields)
	return columns
	
def get_employees():
	query = frappe.db.sql("""SELECT
						name,
						branch,
						ais_akno AS akno,
						ais_isot AS isot,
						ais_isstudent AS isstudent,
						ais_sin_expiry AS sin_expiry,
						ais_issalary AS is_salary,
						ais_adp_no AS adpno,
						employee_name,
						cell_number AS mobile,
						personal_email						
					FROM
						`tabEmployee`
					WHERE
						status = 'Active'""", as_dict=1)
	return query

def get_checkins(employees, filters):
	cycle = frappe.get_doc('Payment Cycle', filters.get('payment_cycle'))
	start_date = cycle.start_date
	end_date = cycle.end_date  + timedelta(days=1)
	checkins = frappe.db.sql("""
								SELECT 
									employee, log_type, time
								FROM
									`tabEmployee Checkin`
								WHERE
									time BETWEEN %(start_date)s AND %(end_date)s
								ORDER BY
									time ASC
									""", {'start_date': start_date, 'end_date': end_date}, as_dict=1)
	return checkins

def get_attendances(employees, filters):
	cycle = frappe.get_doc('Payment Cycle', filters.get('payment_cycle'))
	start_date = cycle.start_date
	end_date = cycle.end_date + timedelta(days=1)
	result = []
	for employee in employees:
		attendances = frappe.db.sql('''SELECT
											attendance.employee,
											attendance.attendance_date,
											checkin.time AS in_time,
											checkout.time AS out_time
										FROM
											`tabAttendance` AS attendance
										LEFT JOIN
											`tabEmployee Checkin` AS checkin ON checkin.attendance = attendance.name AND checkin.log_type = 'IN'
										LEFT JOIN
											`tabEmployee Checkin` AS checkout ON checkout.attendance = attendance.name AND checkout.log_type = 'OUT'
										WHERE
											attendance.employee = %(employee)s AND attendance.attendance_date BETWEEN %(start_date)s AND %(end_date)s
										''', {'employee': employee.name, 'start_date': start_date, 'end_date': end_date}, as_dict=1)
		result.extend(attendances)
	return result
	
@frappe.whitelist()
def get_current_cycle():
	today = datetime.today()
	payment_cycle = frappe.db.get_value('Payment Cycle', filters={'start_date': ['<=', today], 'end_date': ['>=', today]})
	if payment_cycle:
		return payment_cycle
	else:
		''
