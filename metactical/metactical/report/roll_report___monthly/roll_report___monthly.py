# Copyright (c) 2013, Techlift Technologies and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from datetime import datetime, timedelta

def execute(filters=None):
	columns, data = [], []
	#Check filters. Start date = Monday & End date = Sunday
	start_day = datetime.strptime(filters.get('start_date'), '%Y-%m-%d').weekday()
	end_day = datetime.strptime(filters.get('end_date'), '%Y-%m-%d').weekday()
	if start_day != 0 and end_day != 6:
		frappe.throw('Error: Start date should be on a Monday and End Date on a Sunday for \
					proper time calculation')
	
	columns = get_columns(filters)
	employees = get_employees()
	checkins = get_checkins(employees, filters)
	for employee in employees:
		total = 0.00
		regular = 0.00
		other = 0.00
		overtime = 0.00
		weekly_total = 0.00
		daily_overtime = 0.00
		weekly_overtime = 0.00
		previous_day = 0 #For making weeklly calculations
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
					employee.update({
						fieldname: round(current_time, 2)
					})
					next_logtype = 'IN'
					
					# Check day of the week. If less then previous day 
					# then means the start of a new week therefore 
					# do weekly calculations
					total = total + timediff
					tday = datetime.strptime(fieldname, '%Y-%m-%d').weekday()
					if tday < previous_day:
						if employee.get('isstudent') and employee.isstudent == 'Yes':
							if weekly_total > 20:
								regular += 20
								other = other + (weekly_total - 20)
							else:
								regular += weekly_total
						# OT calculated if weekly total is over 44 hours for ON 
						# once weekly hours is over 40 hours for QC
						# once weekly hours is over 40 hours for QC
						if employee.get('isot') and employee.isot == 'Yes':
							#Weekly overtime
							if employee.get('state') == 'ON' and weekly_total > 44:
								overtime = overtime + (weekly_total - 44)
							elif employee.get('state') == 'QC' and weekly_total > 40:
								overtime = overtime + (weekly_total - 40)
							elif employee.get('state') == 'BC':
								if weekly_total > 40:
									weekly_overtime = weekly_total - 40
								#Overtime for that day
								if timediff > 8:
									daily_overtime = daily_overtime + (timediff - 8)
								#If daily overtime is greater than weekly then overtime = daily overtime
								if daily_overtime > weekly_overtime:
									overtime += daily_overtime
								else:
									overtime += weekly_overtime
						
						#Reset weekly total
						weekly_total = timediff
						weekly_overtime = 0
						daily_overtime = 0
					else:
						weekly_total += timediff
						#Calculate daily overtime
						if employee.get('isot') == 'Yes' and employee.get('state') == 'BC':
							if timediff > 8:
								daily_overtime = daily_overtime + (timediff - 8)						
					previous_day = tday					
				elif next_logtype == 'IN':
					fieldname = datetime.strftime(checkin.time, "%Y-%m-%d")
					checkintime = checkin.time
					next_logtype = 'OUT'
			elif checkin.employee == employee.name and checkin.log_type != next_logtype:
				if next_logtype == 'OUT':
					fieldname = datetime.strftime(checkin.time, "%Y-%m-%d")
					checkintime = checkin.time
					next_logtype = 'OUT'
		
		#Do weekly calculation for the last week	
		if employee.get('isstudent') and employee.isstudent == 'Yes':
			if weekly_total > 20:
				regular += 20
				other = other + (weekly_total - 20)
			else:
				regular += weekly_total
				
		if employee.get('isot') and employee.isot == 'Yes':
			if employee.get('state') == 'ON' and weekly_total > 44:
				overtime = overtime + (weekly_total - 44)
			elif employee.get('state') == 'QC' and weekly_total > 40:
				overtime = overtime + (weekly_total - 40)
			elif employee.get('state') == 'BC':
				if weekly_total > 40:
					weekly_overtime = weekly_total - 40
				#Overtime for that day
				if timediff > 8:
					daily_overtime = daily_overtime + (timediff - 8)
				#If daily overtime is greater than weekly then overtime = daily overtime
				if daily_overtime > weekly_overtime:
					overtime += daily_overtime
				else:
					overtime += weekly_overtime
			regular = total - overtime
			
		if employee.get("isotherfile") == "Yes":
			regular = 0
			other = 0
			overtime = 0
				
		employee.update({
			"total": round(total, 2),
			"regular": round(regular, 2),
			"other": round(other, 2),
			"overtime": round(overtime, 2)
		})
		
		#Only add employee if total no of hours > 0
		if total > 0:
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
			"fieldname": "isotherfile",
			"label": "IsOtherFile",
			"options": "Yes/nNo",
			"width": 100
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
		}
	]
	
	start_date = datetime.strptime(filters.get('start_date'), '%Y-%m-%d')
	end_date = datetime.strptime(filters.get('end_date'), '%Y-%m-%d')
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
			"fieldname": "overtime",
			"label": "OT",
			"precision": 2,
			"width": 100
		},
		{
			"fieldtype": "Float",
			"fieldname": "other",
			"label": "GoogleSheet",
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
		},
		{
			"fieldtype": "Data",
			"fieldname": "state",
			"label": "Province",
			"width": 80
		},
		{
			"fieldtype": "Small Text",
			"fieldname": "customnotes",
			"label": "CustomNotes",
			"width": 150
		},
		{
			"fieldtype": "Data",
			"fieldname": "adpno",
			"label": "ADP No",
			"width": 100
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
						personal_email,
						ais_isotherfile AS isotherfile,
						ais_customnotes AS customnotes,
						ais_state AS state				
					FROM
						`tabEmployee`
				""", as_dict=1)
	return query

def get_checkins(employees, filters):
	start_date = filters.get('start_date')
	end_date = filters.get('end_date')
	checkins = frappe.db.sql("""
								SELECT 
									employee, log_type, time
								FROM
									`tabEmployee Checkin`
								WHERE
									cast(time as date) BETWEEN %(start_date)s AND %(end_date)s
								ORDER BY
									time ASC
									""", {'start_date': start_date, 'end_date': end_date}, as_dict=1)
	return checkins

def get_attendances(employees, filters):
	start_date = filters.get('start_date')
	end_date = filters.get('end_date')
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
