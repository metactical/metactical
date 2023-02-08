import frappe
import datetime

#Check if logged in user has current pay cycle record
@frappe.whitelist()
def check_current_pay_cycle_record(current_date, current_time):
	user = frappe.session.user
	employee = frappe.db.exists("Employee", {"user_id": user})
	current_shift = None
	
	#Get current pay cycle
	current_pay_cycle_exists = frappe.db.exists("Pay Cycle Record", {
		"from_date": ("<=", current_date),
		"to_date": (">=", current_date)
	})

	#Check shift assignment
	shift_assignment = frappe.db.exists("Shift Assignment", {
		"employee": employee,
		"status": "Active",
		"docstatus": 1
	})

	if employee:
		if shift_assignment:
			shift_type_record = frappe.get_value("Shift Assignment", shift_assignment, "shift_type")
			shift_type = frappe.get_doc("Shift Type", shift_type_record)
			current_shift = shift_type

			if time_difference((current_time), str(shift_type.start_time)) >= 0 and time_difference((current_time), str(shift_type.end_time)) < 0:
				if current_pay_cycle_exists:
					from_date = frappe.get_value("Pay Cycle Record", current_pay_cycle_exists, "from_date")
					to_date = frappe.get_value("Pay Cycle Record", current_pay_cycle_exists, "to_date")

					user_pay_cycle_record_exists = frappe.db.exists("Pay Cycle", {
						"user": user,
						"from_date": from_date,
						"to_date": to_date
					})

					if not user_pay_cycle_record_exists:
						create_user_pay_cycle_record(user, from_date, to_date, current_date, current_time)

					else:
						clockin_log_record_today_exists = frappe.db.exists("Clockin Log", {
							"user": user,
							"date": current_date
						})

						if not clockin_log_record_today_exists:
							create_clockin_log(user, current_date, current_time)

				else:
					frappe.throw("Couldn not find pay cycle period. Contact administrator")
			
			else:
				#frappe.throw("Clockin too early")
				return {
					"clockin_status": 0
				}
		
		else:
			frappe.throw("Shift assignment not found")
	else:
		frappe.throw("User not active employee. Contact Administrator")

	user_pay_cycle_record = frappe.db.exists("Pay Cycle", {
		"user": user,
		"from_date": ("<=", current_date),
		"to_date": (">=", current_date),
	})

	user_pay_cycle = frappe.get_doc("Pay Cycle", user_pay_cycle_record)
	current_pay_cycle = frappe.get_doc("Pay Cycle Record", current_pay_cycle_exists)
	
	previous_pay_cycles_viewable = frappe.db.get_single_value("Time Tracker Settings", "previous_viewable_pay_cycles")
	#frappe.errprint(previous_pay_cycles_viewable)
	pay_cycles = [user_pay_cycle]

	prev_index = 1
	while prev_index <= previous_pay_cycles_viewable:
		previous_pay_cycle_record = frappe.db.exists("Pay Cycle Record", {"idx": current_pay_cycle.idx + prev_index})
		
		if previous_pay_cycle_record:
			previous_pay_cycle = frappe.get_doc("Pay Cycle Record", previous_pay_cycle_record)

			user_previous_pay_cycle_record = frappe.db.exists("Pay Cycle", {
				"user": user,
				"from_date": previous_pay_cycle.from_date,
				"to_date": previous_pay_cycle.to_date
			})

			if user_previous_pay_cycle_record:
				user_previous_pay_cycle = frappe.get_doc("Pay Cycle", user_previous_pay_cycle_record)
				#frappe.errprint(user_previous_pay_cycle)
				pay_cycles.append(user_previous_pay_cycle)

				prev_index += 1

	#frappe.errprint(current_pay_cycle.idx)
	button_activation_delay = frappe.db.get_single_value("Time Tracker Settings", "clockinout_delay")

	return {
		"pay_cycles": pay_cycles, 
		"button_activation_delay": button_activation_delay,
		"clockin_status": 1,
		"current_shift": current_shift
		}

def create_user_pay_cycle_record(user, from_date, to_date, current_date, current_time):
	user_pay_cycle_record = frappe.get_doc({
		"doctype": "Pay Cycle",
		"user": user,
		"from_date": from_date,
		"to_date": to_date
	})

	user_pay_cycle_record.insert()

	#Create child day records
	index = 1
	date_index = from_date 

	while date_index != to_date:
		row = user_pay_cycle_record.append("days", {
			"date": date_index
		})

		row.insert()
		
		date_index = from_date + datetime.timedelta(days=index)
		index += 1

	row = user_pay_cycle_record.append("days", {
		"date": date_index
	})

	row.insert()

	create_clockin_log(user, current_date, current_time)

	frappe.errprint(index)
	frappe.errprint(date_index)
	frappe.errprint(to_date)
	frappe.errprint(date_index == to_date)

def create_clockin_log(user, current_date, from_time):
	clockin_log_record = frappe.get_doc({
		"doctype": "Clockin Log",
		"user": user,
		"date": current_date,
		"from_time": from_time
	})

	clockin_log_record.insert()

@frappe.whitelist()
def update_clockin_log(current_date, to_time):
	user = frappe.session.user

	clockin_log_record = frappe.db.exists("Clockin Log", {
		"user": user,
		"date": current_date,
	})

	clockin_log = frappe.get_doc("Clockin Log", clockin_log_record)
	clockin_log.to_time = to_time
	clockin_log.has_clocked_out = 1
	clockin_log.save()

@frappe.whitelist()
def get_date_details(date):
	user = frappe.session.user

	clockins = frappe.get_all("Clockin Log", filters={"user": user, "date": date, "has_clocked_out": 1}, fields=["name", "from_time", "to_time"])
	
	return {"clockins": clockins}

@frappe.whitelist()
def get_shifts(current_shift_name):
	shifts = frappe.db.get_all("Shift Type", filters={"name": ("!=", current_shift_name)}, fields=["name", "start_time", "end_time"])
	return {"shifts": shifts}

@frappe.whitelist()
def shift_request(date, shift_type):
	user = frappe.session.user
	employee = frappe.db.exists("Employee", {"user_id": user})
	selected_shift_details = frappe.get_doc("Shift Type", shift_type)

	user_doc = frappe.get_doc("User", user)
	username = user_doc.username
	first_name = user_doc.first_name
	last_name = user_doc.last_name
	
	doc = frappe.get_doc({
		"doctype": "Shift Request",
		"shift_type": shift_type,
		"company": "International Camouflage Ltd",
		"from_date": str(datetime.date.today()),
		"employee": employee
	})

	doc.insert()
	frappe.db.commit()

	#frappe.errprint()
	recipients = [f'{doc.approver}']
	frappe.sendmail(
		recipients=recipients,
		subject='Shift Request',
		template='shift_assignment_request',
		args=dict(
			date=str(date),
			check_in=convert_to_12hr(str(selected_shift_details.start_time)[:-3]),
			check_out=convert_to_12hr(str(selected_shift_details.end_time)[:-3]),
			total_hours=time_difference(selected_shift_details.end_time, selected_shift_details.start_time),
			username=username,
			first_name=first_name,
			last_name=last_name,
			url=f'app/shift-request/{doc.name}'
		),
		header="Shift Request"
	)

def convert_to_12hr(time_24hr):
	frappe.errprint(time_24hr)
	time = datetime.datetime.strptime(time_24hr, '%H:%M').strftime('%I:%M %p')
	return time

@frappe.whitelist()
def send_details_change_request(log_name, checkInTime12, checkInTimeMilitary, checkOutTime12, checkOutTimeMilitary, currentCheckIn12, currentCheckOut12, date):
	user = frappe.session.user
	#employee = frappe.db.exists("Employee", {"user_id": user})
	#selected_shift_details = frappe.get_doc("Shift Type", shift_type)

	#frappe.errprint("Log is")
	#frappe.errprint(log_name)

	user_doc = frappe.get_doc("User", user)
	username = user_doc.username
	first_name = user_doc.first_name
	last_name = user_doc.last_name

	requested_total_hours = time_difference(f'{checkOutTimeMilitary}:00', f'{checkInTimeMilitary}:00')
	current_total_hours = frappe.get_value("Clockin Log", log_name, "total_hours")

	#return request_total_hours

	doc = frappe.get_doc({
		"doctype": "Checkin Request Modification",
		"user": user,
		"date": date,
		"current_checkin": currentCheckIn12,
		"current_checkout": currentCheckOut12,
		"current_total_hours": int(current_total_hours),
		"requested_checkin": checkInTime12,
		"requested_checkout": checkOutTime12,
		"requested_total_hours": int(requested_total_hours),
		"log": log_name,
		"status": "Pending",
		"requested_checkin_military": f'{checkInTimeMilitary}:00',
		"requested_checkout_military": f'{checkOutTimeMilitary}:00'
	})

	doc.insert()
	frappe.db.commit()

	recipients = frappe.db.get_single_value("Time Tracker Settings", "checkin_approver")
	frappe.sendmail(
		recipients=recipients,
		subject='Change Clockin details',
		template='send_details_change_request',
		args=dict(
			date=str(date),
			check_in=currentCheckIn12,
			check_out=currentCheckOut12,
			total_hours=current_total_hours,
			checkInTime12=checkInTime12,
			checkOutTime12=checkOutTime12,
			requestedTotalHours=requested_total_hours,
			username=username,
			first_name=first_name,
			last_name=last_name,
			approve_url=f'approve?req={doc.name}',
			decline_url=f'decline?req={doc.name}'
		),
		header="Checkin Modification Request"
	)

@frappe.whitelist()
def decline_details_change_request(request_name):
	req = frappe.get_doc("Checkin Request Modification", request_name)
	req.status = "Declined"
	req.save()

	return "success"

@frappe.whitelist()
def approve_details_change_request(request_name):
	req = frappe.get_doc("Checkin Request Modification", request_name)
	req.status = "Approved"
	req.save()

	clockin_log = frappe.get_doc("Clockin Log", req.log)
	clockin_log.from_time = req.requested_checkin_military
	clockin_log.to_time = req.requested_checkout_military
	clockin_log.save()

	return "success"

def time_difference(time1, time2):
	# convert times to datetime objects
	today = datetime.date.today()
	time1 = datetime.datetime.strptime(f'{today} {time1}', "%Y-%m-%d %H:%M:%S")
	time2 = datetime.datetime.strptime(f'{today} {time2}', "%Y-%m-%d %H:%M:%S")
	
	# calculate the difference between times
	time_diff = time1 - time2
	
	# convert difference to hours
	time_diff_hours = time_diff.total_seconds() / 3600
	
	return time_diff_hours