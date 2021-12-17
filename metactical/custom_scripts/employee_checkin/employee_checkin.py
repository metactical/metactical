import frappe
from frappe.utils.password import check_password
from frappe.utils import now, cint, get_datetime
#from erpnext.hr.doctype.employee_checkin.employee_checkin import add_log_based_on_employee_field

@frappe.whitelist(allow_guest=True)
def check_user(user):
	user_type = frappe.db.get_value("User", user, "user_type")
	if user_type and user_type == "System User":
		employee = frappe.db.get_value('Employee', {'user_id': user}, 'name')
		if employee:
			status = frappe.db.sql('''SELECT 
										log_type
									FROM 
										`tabEmployee Checkin` AS checkin 
									WHERE 
										checkin.employee=%(user)s
									ORDER BY time DESC LIMIT 1''', {"user": employee}, as_dict=1)
			if status:
				return {'is_user': 1, 'last_status': status[0].log_type}
			else:
				return {'is_user': 1, 'last_status': 'OUT'}
		else:
			return {'is_user': 0}
	else:
		return {'is_user': 0}
		
@frappe.whitelist(allow_guest=True)
def login_checkin(user, password, logged_in='False'):
	if logged_in == 'False':
		#Check user password. Will raise error if incorrect
		check_user = check_password(user, password)
	
	employee = frappe.db.get_value("Employee", {'user_id': user}, 'name')
	if employee:
		last_status = frappe.db.sql('''SELECT 
						log_type
					FROM 
						`tabEmployee Checkin` AS checkin 
					WHERE 
						checkin.employee=%(user)s
					ORDER BY time DESC LIMIT 1''', {"user": employee}, as_dict=1)
		if len(last_status) > 0:
			if last_status[0].log_type == 'OUT':
				add_log_based_on_employee_field(employee, frappe.utils.now(), log_type='IN', employee_fieldname='name')
				return {"next_log": 'Check Out'}
			elif last_status[0].log_type == 'IN':
				add_log_based_on_employee_field(employee, frappe.utils.now(), log_type='OUT', employee_fieldname='name')
				#Get last two checkins
				logs = frappe.db.sql('''SELECT *
											FROM 
												`tabEmployee Checkin` 
											WHERE 
												employee=%(employee)s AND attendance IS NULL
											ORDER BY time DESC LIMIT 2''', {'employee': employee}, as_dict=1)
				if len(logs) == 2:
					mark_attendance_and_link_log(logs, 'Present', logs[1].time.strftime('%Y-%m-%d'),)
				return {"next_log": 'Checkin'}
		else:
			add_log_based_on_employee_field(employee, frappe.utils.now(), log_type='IN', employee_fieldname='name')
			return {"next_log": 'Checkout'}
				
@frappe.whitelist(allow_guest=True)
def add_log_based_on_employee_field(employee_field_value, timestamp, device_id=None, log_type=None, skip_auto_attendance=0, employee_fieldname='attendance_device_id'):
	"""Finds the relevant Employee using the employee field value and creates a Employee Checkin.

	:param employee_field_value: The value to look for in employee field.
	:param timestamp: The timestamp of the Log. Currently expected in the following format as string: '2019-05-08 10:48:08.000000'
	:param device_id: (optional)Location / Device ID. A short string is expected.
	:param log_type: (optional)Direction of the Punch if available (IN/OUT).
	:param skip_auto_attendance: (optional)Skip auto attendance field will be set for this log(0/1).
	:param employee_fieldname: (Default: attendance_device_id)Name of the field in Employee DocType based on which employee lookup will happen.
	"""

	if not employee_field_value or not timestamp:
		frappe.throw(_("'employee_field_value' and 'timestamp' are required."))

	employee = frappe.db.get_values("Employee", {employee_fieldname: employee_field_value}, ["name", "employee_name", employee_fieldname], as_dict=True)
	if employee:
		employee = employee[0]
	else:
		frappe.throw(_("No Employee found for the given employee field value. '{}': {}").format(employee_fieldname,employee_field_value))

	doc = frappe.new_doc("Employee Checkin")
	doc.employee = employee.name
	doc.employee_name = employee.employee_name
	doc.time = timestamp
	doc.device_id = device_id
	doc.log_type = log_type
	if cint(skip_auto_attendance) == 1: doc.skip_auto_attendance = '1'
	doc.insert(ignore_permissions=True)

	return doc
	
def mark_attendance_and_link_log(logs, attendance_status, attendance_date, working_hours=None, late_entry=False, early_exit=False, shift=None):
	"""Creates an attendance and links the attendance to the Employee Checkin.
	Note: If attendance is already present for the given date, the logs are marked as skipped and no exception is thrown.

	:param logs: The List of 'Employee Checkin'.
	:param attendance_status: Attendance status to be marked. One of: (Present, Absent, Half Day, Skip). Note: 'On Leave' is not supported by this function.
	:param attendance_date: Date of the attendance to be created.
	:param working_hours: (optional)Number of working hours for the given date.
	"""
	log_names = [x.name for x in logs]
	employee = logs[0].employee
	if attendance_status == 'Skip':
		frappe.db.sql("""update `tabEmployee Checkin`
			set skip_auto_attendance = %s
			where name in %s""", ('1', log_names))
		return None
	elif attendance_status in ('Present', 'Absent', 'Half Day'):
		employee_doc = frappe.get_doc('Employee', employee)
		if not frappe.db.exists('Attendance', {'employee':employee, 'attendance_date':attendance_date, 'docstatus':('!=', '2')}):
			doc_dict = {
				'doctype': 'Attendance',
				'employee': employee,
				'attendance_date': attendance_date,
				'status': attendance_status,
				'working_hours': working_hours,
				'company': employee_doc.company,
				'shift': shift,
				'late_entry': late_entry,
				'early_exit': early_exit
			}
			attendance = frappe.get_doc(doc_dict).insert(ignore_permissions=True)
			attendance.submit()
			frappe.db.sql("""update `tabEmployee Checkin`
				set attendance = %s
				where name in %s""", (attendance.name, log_names))
			return attendance
		else:
			frappe.db.sql("""update `tabEmployee Checkin`
				set skip_auto_attendance = %s
				where name in %s""", ('1', log_names))
			return None
	else:
		frappe.throw(_('{} is an invalid Attendance Status.').format(attendance_status))

