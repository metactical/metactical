# Copyright (c) 2013, Techlift Technologies and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from datetime import datetime, timedelta, date
from dateutil.relativedelta import relativedelta

def execute(filters=None):
	columns, data = [], []
	columns = [
		{
			"fieldtype": "Data",
			"fieldname": "date",
			"label": "Date",
			"width": 150
		},
		{
			"fieldtype": "Time",
			"fieldname": "login",
			"label": "Login",
			"width": 150
		},
		{
			"fieldtype": "Time",
			"fieldname": "logout",
			"label": "Logout",
			"width": 150
		},
		{
			"fieldtype": "Float",
			"fieldname": "total_hours",
			"label": "Total Hours",
			"width": 150
		}
	]
	
	employee = frappe.db.get_value('Employee', {"user_id": frappe.session.user}, "name")
	checkins = get_checkins(employee)
	total = 0.00
	next_logtype = 'IN'
	# Do a checkin pair check. For every checkin there must be accompanying checkout.
	# If a checkin followed by another checkin thene the previous checkin is ignored.
	# If acheckout followed by another checkout then the second checkout is ignored
	row = {}
	for checkin in checkins:
		if checkin.log_type == next_logtype:
			if next_logtype == 'OUT':
				row['logout'] = datetime.strftime(checkin.time, "%H:%M")
				timediff = (checkin.time - row['login_t']).total_seconds() / 3600
				row['total_hours'] = timediff
				data.append(row)
				next_logtype = 'IN'
				row = {}
			elif next_logtype == 'IN':
				row['date'] = datetime.strftime(checkin.time, "%d-%b-%Y")
				row['login'] = datetime.strftime(checkin.time, "%H:%M")
				row['login_t'] = checkin.time
				next_logtype = 'OUT'
		elif checkin.log_type != next_logtype:
			if next_logtype == 'OUT':
				row['date'] = datetime.strftime(checkin.time, "%d-%b-%Y")
				row['login'] = datetime.strftime(checkin.time, "%H:%M")
				row['login_t'] = checkin.time
				next_logtype = 'OUT'
	#Finally if last is a checkin, show it
	if next_logtype == 'OUT' and len(row) > 0:
		data.append(row)
		
	#Finally reverse to have the latest date on top
	data.reverse()
	return columns, data

def get_checkins(employee):
	end_date = datetime.now()
	start_date = end_date - relativedelta(months=2)
	checkins = frappe.db.sql("""
								SELECT 
									employee, log_type, time
								FROM
									`tabEmployee Checkin`
								WHERE
									employee = %(employee)s AND time >= %(start_date)s AND time <= %(end_date)s
								ORDER BY
									time ASC
									""", {'employee': employee, 'start_date': start_date, 
									'end_date': end_date}, as_dict=1)
	return checkins
