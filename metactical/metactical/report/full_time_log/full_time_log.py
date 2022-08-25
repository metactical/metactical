# Copyright (c) 2022, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
from datetime import datetime

def execute(filters=None):
	columns, data = [], []
	checkins = get_checkins(filters)
	data, no_of_columns = organize_data(checkins)
	columns = get_columns(no_of_columns)
	return columns, data

def get_columns(no_of_columns):
	columns = [
		{
			"fieldname": "employee",
			"label": "Employee",
			"fieldtype": "Link",
			"options": "Employee",
			"width": 250
		},
		{
			"fieldname": "date",
			"label": "Date",
			"fieldtype": "Date",
			"width": 100
		},
		{
			"fieldname": "total",
			"label": "Total",
			"fieldtype": "Float",
			"precision": 2,
			"width": 80
		}
	]
	
	current_columns = 1
	while no_of_columns > current_columns:
		columns.extend([
			{
				"fieldname": 'login_' + str(current_columns),
				"label": 'Log In',
				"fieldtype": "Data",
				"width": 100
			},
			{
				"fieldname": 'logout_' + str(current_columns),
				"label": 'Log Out',
				"fieldtype": "Data",
				"width": 100
			}
		])
		current_columns += 1
	return columns

def organize_data(data):
	no_of_columns = 0
	total_columns = 0
	next_logtype = 'IN'
	rdata = []
	current_row = {}
	current_date = ''
	in_time = None
	total_time = 0
	for row in data:
		if current_date != datetime.strftime(row.time, '%d-%b-%Y'):
			current_date = datetime.strftime(row.time, '%d-%b-%Y')
			no_of_columns = 1
			fieldname = 'log' + row.log_type.lower() + '_' + str(no_of_columns)
			if current_row != {}:
				current_row.update({"total": total_time})
				total_time = 0
				rdata.append(current_row)
			in_time = row.time
			current_row = {
							"employee": row.employee,
							"employee_name": row.employee_name,
							'date': current_date,
							fieldname: datetime.strftime(row.time, "%H:%M")
			}
		else:
			fieldname = 'log' + row.log_type.lower() + '_' + str(no_of_columns)
			current_row.update({
				fieldname: datetime.strftime(row.time, '%H:%M')
			})
			if row.log_type == 'OUT':
				total_time += ((row.time - in_time).total_seconds() / 3600)
				no_of_columns += 1
				if no_of_columns > total_columns:
					total_columns = no_of_columns
			else:
				in_time = row.time
	#Add last row
	current_row.update({"total": total_time})
	rdata.append(current_row)
	return rdata, total_columns
			

def get_checkins(filters):
	start_date = filters.get('start_date')
	end_date = filters.get('end_date')
	employee = filters.get('employee')
	checkins = frappe.db.sql("""
								SELECT 
									employee, employee_name, log_type, time
								FROM
									`tabEmployee Checkin`
								WHERE
									cast(time as date) BETWEEN %(start_date)s AND %(end_date)s
									AND employee = %(employee)s
								ORDER BY
									time ASC
									""", {'start_date': start_date, 'end_date': end_date, "employee": employee}, 
						as_dict=1)
	return checkins
