import frappe

def scrub_data():
	scrub_delivery_notes()
	scrub_payment_entries()
	scrub_sales_orders()
	scrub_sales_invoices()
	scrub_pick_lists()
	scrub_contacts()
	scrub_address()
	scrub_customer()

def scrub_user_and_employee():
	scrub_employee_checkin()
	scrub_shift_assignment()
	scrub_employee()
	scrub_clockin_log()
	scrub_checkin_request_modification()
	scrub_user_permission()
	scrub_employee_from_user_permission()
	scrub_route_history()
	scrub_activity_log()
	scrub_access_log()
	scrub_user()

	
def scrub_delivery_notes():
	max_offset = frappe.db.sql("""
					SELECT
						COUNT(delivery_note.name) AS total
					FROM
						`tabDelivery Note` AS delivery_note
					""", as_dict=1)[0].total;
	
	current_offset = 0
	while current_offset < max_offset:
		deliveries = frappe.db.sql(f"""
			SELECT 
				delivery_note.name 
			FROM 
				`tabDelivery Note` AS delivery_note
			ORDER BY 
				delivery_note.creation
			LIMIT 1000
			OFFSET {current_offset}
		""", as_dict=1)
		
		delivery_notes = ""
		for row in deliveries:
			delivery_notes += f"'{row.name}',"
		delivery_notes = delivery_notes[:-1]
		
		frappe.db.sql(f"""
			UPDATE `tabDelivery Note` delivery
			LEFT JOIN `tabCustomer` customer ON delivery.customer = customer.name
			LEFT JOIN `tabAddress` address ON delivery.customer_address = address.name
			LEFT JOIN `tabAddress` address2 ON delivery.shipping_address_name = address2.name
			LEFT JOIN `tabContact` contact ON delivery.contact_person = contact.name
			SET
				delivery.customer = MD5(delivery.customer),
				delivery.customer_name = CONCAT(SUBSTRING(MD5(customer.first_name), 1, 8), ' ', SUBSTRING(MD5(customer.last_name), 1, 8)),
				delivery.title = CONCAT(SUBSTRING(MD5(customer.first_name), 1, 8), ' ', SUBSTRING(MD5(customer.last_name), 1, 8)),
				delivery.contact_mobile = SUBSTRING(CAST(SHA(delivery.contact_mobile) AS CHAR), 1, 10),
				delivery.contact_email = CONCAT(SUBSTRING(MD5(delivery.contact_email), 1, 8), '@test.com'),
				delivery.contact_person = MD5(delivery.contact_person),
				delivery.customer_address = MD5(delivery.customer_address),
				delivery.shipping_address_name = MD5(delivery.shipping_address_name),
				delivery.contact_display = CONCAT(SUBSTRING(MD5(contact.first_name), 1, 8), ' ', SUBSTRING(MD5(contact.last_name), 1, 8)),
				delivery.address_display = CONCAT(SUBSTRING(MD5(address.address_line1), 1, 8), '<br>', address.city, '<br>', address.state, '<br>', address.pincode, '<br>', address.country, '<br>Phone: ', SUBSTRING(CAST(SHA(address.phone) AS CHAR), 1, 10), '<br>Email: ', CONCAT(SUBSTRING(MD5(address.email_id), 1, 8), '@test.com')),
				delivery.shipping_address = CONCAT(SUBSTRING(MD5(address2.address_line1), 1, 8), '<br>', address2.city, '<br>', address2.state, '<br>', address2.pincode, '<br>', address2.country, '<br>Phone: ', SUBSTRING(CAST(SHA(address2.phone) AS CHAR), 1, 10), '<br>Email: ', CONCAT(SUBSTRING(MD5(address2.email_id), 1, 8), '@test.com'))
			WHERE
				delivery.name in ({delivery_notes})
		""")
		
		current_offset += 1000
	print("Delivery notes scrubd successfully")

def scrub_payment_entries():
	max_offset = frappe.db.sql("""
					SELECT
						COUNT(payment_entry.name) AS total
					FROM
						`tabPayment Entry` AS payment_entry
					""", as_dict=1)[0].total;
	
	current_offset = 0
	while current_offset < max_offset:
		payments = frappe.db.sql(f"""
			SELECT 
				payment_entry.name 
			FROM 
				`tabPayment Entry` AS payment_entry
			ORDER BY 
				payment_entry.creation
			LIMIT 1000
			OFFSET {current_offset}
		""", as_dict=1)
	
		payment_entries = ""
		for row in payments:
			payment_entries += f"'{row.name}',"
		payment_entries = payment_entries[:-1]
		
		frappe.db.sql(f"""
			UPDATE `tabPayment Entry` payment
			LEFT JOIN `tabCustomer` AS customer ON customer.name = payment.party
			LEFT JOIN `tabContact` AS contact ON contact.name = payment.contact_person
			SET
				payment.party = MD5(payment.party),
				payment.party_name = CONCAT(SUBSTRING(MD5(customer.first_name), 1, 8), ' ', SUBSTRING(MD5(customer.last_name), 1, 8)),
				payment.title = CONCAT(SUBSTRING(MD5(customer.first_name), 1, 8), ' ', SUBSTRING(MD5(customer.last_name), 1, 8)),
				payment.remarks = SUBSTRING(MD5(payment.remarks), 1, 8),
				payment.contact_person = MD5(payment.contact_person),
				payment.contact_email = CONCAT(SUBSTRING(MD5(payment.contact_email), 1, 8), '@test.com')
			WHERE
				payment.party_type = 'Customer' AND payment.name in ({payment_entries})
		""")
		current_offset += 1000
	print("Payment Entries scrubd successfully")
		
def scrub_sales_orders():
	max_offset = frappe.db.sql("""
					SELECT
						COUNT(sales_order.name) AS total
					FROM
						`tabSales Order` AS sales_order
					""", as_dict=1)[0].total;
	
	current_offset = 0
	while current_offset < max_offset:
		orders = frappe.db.sql(f"""
			SELECT 
				sales_order.name 
			FROM 
				`tabSales Order` AS sales_order
			ORDER BY 
				sales_order.creation
			LIMIT 1000
			OFFSET {current_offset}
		""", as_dict=1)
	
		sales_orders = ""
		for row in orders:
			sales_orders += f"'{row.name}',"
		sales_orders = sales_orders[:-1]
		
		frappe.db.sql(f"""
			UPDATE `tabSales Order` sorder
			LEFT JOIN `tabCustomer` customer ON sorder.customer = customer.name
			LEFT JOIN `tabAddress` address ON sorder.customer_address = address.name
			LEFT JOIN `tabAddress` address2 ON sorder.shipping_address_name = address2.name
			LEFT JOIN `tabContact` contact ON sorder.contact_person = contact.name
			SET
				sorder.customer = MD5(sorder.customer),
				sorder.title = CONCAT(SUBSTRING(MD5(customer.first_name), 1, 8), ' ', SUBSTRING(MD5(customer.last_name), 1, 8)),
				sorder.customer_name = CONCAT(SUBSTRING(MD5(customer.first_name), 1, 8), ' ', SUBSTRING(MD5(customer.last_name), 1, 8)),
				sorder.contact_mobile = SUBSTRING(CAST(SHA(sorder.contact_mobile) AS CHAR), 1, 10),
				sorder.contact_email = CONCAT(SUBSTRING(MD5(sorder.contact_email), 1, 8), '@test.com'),
				sorder.contact_person = MD5(sorder.contact_person),
				sorder.customer_address = MD5(sorder.customer_address),
				sorder.shipping_address_name = MD5(sorder.shipping_address_name),
				sorder.contact_display = CONCAT(SUBSTRING(MD5(contact.first_name), 1, 8), ' ', SUBSTRING(MD5(contact.last_name), 1, 8)),
				sorder.address_display = CONCAT(SUBSTRING(MD5(address.address_line1), 1, 8), '<br>', address.city, '<br>', address.state, '<br>', address.pincode, '<br>', address.country, '<br>Phone: ', SUBSTRING(CAST(SHA(address.phone) AS CHAR), 1, 10), '<br>Email: ', CONCAT(SUBSTRING(MD5(address.email_id), 1, 8), '@test.com')),
				sorder.shipping_address = CONCAT(SUBSTRING(MD5(address2.address_line1), 1, 8), '<br>', address2.city, '<br>', address2.state, '<br>', address2.pincode, '<br>', address2.country, '<br>Phone: ', SUBSTRING(CAST(SHA(address2.phone) AS CHAR), 1, 10), '<br>Email: ', CONCAT(SUBSTRING(MD5(address2.email_id), 1, 8), '@test.com'))
			WHERE sorder.name in ({sales_orders})
		""")
		current_offset += 1000
	print("Sales Orders scrubd successfully")

def scrub_sales_invoices():
	max_offset = frappe.db.sql("""
					SELECT
						COUNT(sales_invoice.name) AS total
					FROM
						`tabSales Invoice` AS sales_invoice
					""", as_dict=1)[0].total;
	
	current_offset = 0
	while current_offset < max_offset:
		invoices = frappe.db.sql(f"""
			SELECT 
				sales_invoice.name 
			FROM 
				`tabSales Invoice` AS sales_invoice
			ORDER BY 
				sales_invoice.creation
			LIMIT 1000
			OFFSET {current_offset}
		""", as_dict=1)
	
		sales_invoices = ""
		for row in invoices:
			sales_invoices += f"'{row.name}',"
		sales_invoices = sales_invoices[:-1]
		
		frappe.db.sql(f"""
			UPDATE `tabSales Invoice` invoice
			LEFT JOIN `tabCustomer` customer ON invoice.customer = customer.name
			LEFT JOIN `tabAddress` address ON invoice.customer_address = address.name
			LEFT JOIN `tabAddress` address2 ON invoice.shipping_address_name = address2.name
			LEFT JOIN `tabContact` contact ON invoice.contact_person = contact.name
			SET
				invoice.customer = MD5(invoice.customer),
				invoice.customer_name = CONCAT(SUBSTRING(MD5(customer.first_name), 1, 8), ' ', SUBSTRING(MD5(customer.last_name), 1, 8)),
				invoice.title = CONCAT(SUBSTRING(MD5(customer.first_name), 1, 8), ' ', SUBSTRING(MD5(customer.last_name), 1, 8)),
				invoice.contact_mobile = SUBSTRING(CAST(SHA(invoice.contact_mobile) AS CHAR), 1, 10),
				invoice.contact_email = CONCAT(SUBSTRING(MD5(invoice.contact_email), 1, 8), '@test.com'),
				invoice.contact_person = MD5(invoice.contact_person),
				invoice.customer_address = MD5(invoice.customer_address),
				invoice.shipping_address_name = MD5(invoice.shipping_address_name),
				invoice.contact_display = CONCAT(SUBSTRING(MD5(contact.first_name), 1, 8), ' ', SUBSTRING(MD5(contact.last_name), 1, 8)),
				invoice.address_display = CONCAT(SUBSTRING(MD5(address.address_line1), 1, 8), '<br>', address.city, '<br>', address.state, '<br>', address.pincode, '<br>', address.country, '<br>Phone: ', SUBSTRING(CAST(SHA(address.phone) AS CHAR), 1, 10), '<br>Email: ', CONCAT(SUBSTRING(MD5(address.email_id), 1, 8), '@test.com')),
				invoice.shipping_address = CONCAT(SUBSTRING(MD5(address2.address_line1), 1, 8), '<br>', address2.city, '<br>', address2.state, '<br>', address2.pincode, '<br>', address2.country, '<br>Phone: ', SUBSTRING(CAST(SHA(address2.phone) AS CHAR), 1, 10), '<br>Email: ', CONCAT(SUBSTRING(MD5(address2.email_id), 1, 8), '@test.com'))
			WHERE
				invoice.name in ({sales_invoices})
		""")
		current_offset += 1000
	print("Sales Invoices scrubd successfully")

def scrub_pick_lists():
	max_offset = frappe.db.sql("""
					SELECT
						COUNT(pick_list.name) AS total
					FROM
						`tabPick List` AS pick_list
					""", as_dict=1)[0].total;
	
	current_offset = 0
	while current_offset < max_offset:
		lists = frappe.db.sql(f"""
			SELECT 
				pick_list.name 
			FROM 
				`tabPick List` AS pick_list
			ORDER BY 
				pick_list.creation
			LIMIT 1000
			OFFSET {current_offset}
		""", as_dict=1)
	
		pick_lists = ""
		for row in lists:
			pick_lists += f"'{row.name}',"
		pick_lists = pick_lists[:-1]
		
		frappe.db.sql(f"""
			UPDATE `tabPick List` picklist
			LEFT JOIN `tabCustomer` customer ON customer.name = picklist.customer
			SET
				picklist.customer = MD5(picklist.customer),
				picklist.customer_name = CONCAT(SUBSTRING(MD5(customer.first_name), 1, 8), ' ', SUBSTRING(MD5(customer.last_name), 1, 8))
			WHERE
				picklist.name in ({pick_lists})
		""")
		current_offset += 1000
	print("Pick Lists scrubd successfully")

def scrub_contacts():
	max_offset = frappe.db.sql("""
					SELECT
						COUNT(contact.name) AS total
					FROM
						`tabContact` AS contact
					""", as_dict=1)[0].total;
	
	current_offset = 0
	while current_offset < max_offset:
		contacts = frappe.db.sql(f"""
			SELECT 
				contact.name 
			FROM 
				`tabContact` AS contact
			ORDER BY 
				contact.creation
			LIMIT 1000
			OFFSET {current_offset}
		""", as_dict=1)
	
		contacts_sql = ""
		for row in contacts:
			row_name = row.name.replace("'", "''")
			contacts_sql += "'" + row_name + "',"
		contacts_sql = contacts_sql[:-1]
		
		frappe.db.sql(f"""
			UPDATE `tabContact Email` contact_email 
			LEFT JOIN `tabContact` contact ON contact_email.parent = contact.name 
			SET
				contact_email.parent = MD5(contact_email.parent),
				contact_email.email_id = CONCAT(SUBSTRING(MD5(contact_email.email_id), 1, 8), '@test.com')
			WHERE
				contact.name in ({contacts_sql})
		""")
		
		frappe.db.sql(f"""
			UPDATE `tabContact Phone` contact_phone 
			LEFT JOIN `tabContact` contact ON contact_phone.parent = contact.name 
			SET
				contact_phone.parent = MD5(contact_phone.parent),
				contact_phone.phone = SUBSTRING(CAST(SHA(contact_phone.phone) AS CHAR), 1, 10)
			WHERE
				contact.name in ({contacts_sql})
		""")
		
		frappe.db.sql(f"""
			UPDATE `tabDynamic Link` dynamic_link
			LEFT JOIN `tabContact` contact ON dynamic_link.parent = contact.name
			LEFT JOIN `tabCustomer` customer ON customer.name = dynamic_link.link_name
			SET
				dynamic_link.link_name = MD5(dynamic_link.link_name),
				dynamic_link.link_title = CONCAT(SUBSTRING(MD5(contact.first_name), 1, 8), ' ', SUBSTRING(MD5(contact.last_name), 1, 8)),
				dynamic_link.parent = MD5(dynamic_link.parent)
			WHERE
				dynamic_link.link_doctype = 'Customer' AND contact.name in ({contacts_sql})
		""")
		
		frappe.db.sql(f"""
			UPDATE `tabContact` SET
				first_name = SUBSTRING(MD5(first_name), 1, 8),
				last_name = SUBSTRING(MD5(last_name), 1, 8),
				name = MD5(name),
				phone = SUBSTRING(CAST(SHA(phone) AS CHAR), 1, 10),
				mobile_no = SUBSTRING(CAST(SHA(mobile_no) AS CHAR), 1, 10),
				email_id = CONCAT(SUBSTRING(MD5(email_id), 1, 8), '@test.com')
			WHERE
				name in ({contacts_sql})
		""")
		current_offset += 1000
	print("Contacts scrubd successfully")

def scrub_address():
	max_offset = frappe.db.sql("""
					SELECT
						COUNT(address.name) AS total
					FROM
						`tabAddress` AS address
					""", as_dict=1)[0].total;
	
	current_offset = 0
	while current_offset < max_offset:
		address = frappe.db.sql(f"""
			SELECT 
				address.name 
			FROM 
				`tabAddress` AS address
			ORDER BY 
				address.creation
			LIMIT 1000
			OFFSET {current_offset}
		""", as_dict=1)
	
		address_sql = ""
		for row in address:
			row_name = row.name.replace("'", "''")
			address_sql += "'" + row_name + "',"
		address_sql = address_sql[:-1]
		
		frappe.db.sql(f"""
			UPDATE `tabDynamic Link` dynamic_link
			LEFT JOIN `tabCustomer` customer ON dynamic_link.link_name = customer.name
			LEFT JOIN `tabAddress` address ON dynamic_link.parent = address.name
			SET
				dynamic_link.link_name = MD5(dynamic_link.link_name),
				dynamic_link.link_title = CONCAT(SUBSTRING(MD5(customer.first_name), 1, 8), ' ', SUBSTRING(MD5(customer.last_name), 1, 8)),
				dynamic_link.parent = MD5(dynamic_link.parent)
			WHERE
				dynamic_link.link_doctype = 'Customer' AND dynamic_link.parenttype = 'Address'
				AND address.name in ({address_sql})
		""")
		
		frappe.db.sql(f"""
			UPDATE `tabAddress` address
			SET
				address.address_title = MD5(address.address_title),
				address.name = MD5(address.name),
				address.ifw_first_name = SUBSTRING(MD5(address.ifw_first_name), 1, 8),
				address.ifw_last_name = SUBSTRING(MD5(address.ifw_last_name), 1, 8),
				address.address_line1 = SUBSTRING(MD5(address.address_line1), 1, 8),
				address.address_line2 = SUBSTRING(MD5(address.address_line2), 1, 8),
				address.email_id = CONCAT(SUBSTRING(MD5(address.email_id), 1, 8), '@test.com'),
				address.phone = SUBSTRING(CAST(SHA(address.phone) AS CHAR), 1, 10)
			WHERE address.name in ({address_sql})
		""")
		current_offset += 1000
	print("Addresses scrubd successfully")


def scrub_customer():
	max_offset = frappe.db.sql("""
					SELECT
						COUNT(customer.name) AS total
					FROM
						`tabCustomer` AS customer
					""", as_dict=1)[0].total;
	
	current_offset = 0
	while current_offset < max_offset:
		customers = frappe.db.sql(f"""
			SELECT 
				customer.name 
			FROM 
				`tabCustomer` AS customer
			ORDER BY 
				customer.creation
			LIMIT 1000
			OFFSET {current_offset}
		""", as_dict=1)
	
		customer_sql = ""
		for row in customers:
			row_name = row.name.replace("'", "''")
			customer_sql += "'" + row_name + "',"
		customer_sql = customer_sql[:-1]
		
		frappe.db.sql(f"""
			UPDATE `tabCustomer` customer SET 
				first_name = SUBSTRING(MD5(first_name), 1, 8),
				last_name = SUBSTRING(MD5(last_name), 1, 8),
				name = MD5(name),
				customer_name = CONCAT(first_name, ' ', last_name),
				ifw_email = CONCAT(SUBSTRING(MD5(ifw_email), 1, 8), '@test.com'),
				customer_primary_contact = MD5(customer_primary_contact),
				mobile_no = SUBSTRING(CAST(SHA(mobile_no) AS CHAR), 1, 10),
				email_id = CONCAT(SUBSTRING(MD5(email_id), 1, 8), '@test.com')
			WHERE 
				customer.last_name IS NOT NULL AND customer.last_name != "" AND customer.name in ({customer_sql})
		""")
		current_offset += 1000
	print("Customers scrubd successfully")

def scrub_employee_checkin():
	max_offset = frappe.db.sql("""
					SELECT
						COUNT(employee_checkin.name) AS total
					FROM
						`tabEmployee Checkin` AS employee_checkin
					""", as_dict=1)[0].total;
	
	current_offset = 0
	while current_offset < max_offset:
		checkins = frappe.db.sql(f"""
			SELECT 
				employee_checkin.name 
			FROM 
				`tabEmployee Checkin` AS employee_checkin
			ORDER BY 
				employee_checkin.creation
			LIMIT 1000
			OFFSET {current_offset}
		""", as_dict=1)
	
		employee_checkins = ""
		for row in checkins:
			employee_checkins += f"'{row.name}',"
		employee_checkins = employee_checkins[:-1]
		
		frappe.db.sql(f"""
			UPDATE `tabEmployee Checkin` employee_checkin
			SET
				employee_checkin.employee = MD5(employee_checkin.employee),
				employee_checkin.employee_name = SUBSTRING(MD5(employee_checkin.employee_name), 1, 8)
			WHERE
				employee_checkin.name in ({employee_checkins})
		""")
		current_offset += 1000
	print("Employee Checkins scrubd successfully")

def scrub_shift_assignment():
	max_offset = frappe.db.sql("""
					SELECT
						COUNT(shift_assignment.name) AS total
					FROM
						`tabShift Assignment` AS shift_assignment
					""", as_dict=1)[0].total;
	
	current_offset = 0
	while current_offset < max_offset:
		assignments = frappe.db.sql(f"""
			SELECT 
				shift_assignment.name 
			FROM 
				`tabShift Assignment` AS shift_assignment
			ORDER BY 
				shift_assignment.creation
			LIMIT 1000
			OFFSET {current_offset}
		""", as_dict=1)
	
		shift_assignments = ""
		for row in assignments:
			shift_assignments += f"'{row.name}',"
		shift_assignments = shift_assignments[:-1]
		
		frappe.db.sql(f"""
			UPDATE `tabShift Assignment` shift_assignment
			SET
				shift_assignment.employee = MD5(shift_assignment.employee),
				shift_assignment.employee_name = SUBSTRING(MD5(shift_assignment.employee_name), 1, 8)
			WHERE
				shift_assignment.name in ({shift_assignments})
		""")
		current_offset += 1000
	print("Shift Assignments scrubd successfully")

def scrub_employee():
	max_offset = frappe.db.sql("""
					SELECT
						COUNT(employee.name) AS total
					FROM
						`tabEmployee` AS employee
					""", as_dict=1)[0].total;
	
	current_offset = 0
	while current_offset < max_offset:
		employees = frappe.db.sql(f"""
			SELECT 
				employee.name 
			FROM 
				`tabEmployee` AS employee
			ORDER BY 
				employee.creation
			LIMIT 1000
			OFFSET {current_offset}
		""", as_dict=1)
	
		employee_sql = ""
		for row in employees:
			row_name = row.name.replace("'", "''")
			employee_sql += "'" + row_name + "',"
		employee_sql = employee_sql[:-1]
		
		frappe.db.sql(f"""
			UPDATE `tabEmployee` employee SET 
				first_name = SUBSTRING(MD5(first_name), 1, 8),
				last_name = SUBSTRING(MD5(last_name), 1, 8),
				name = MD5(name),
				employee_name = CONCAT(first_name, ' ', last_name),
				personal_email = CONCAT(SUBSTRING(MD5(personal_email), 1, 8), '@test.com'),
				company_email = CONCAT(SUBSTRING(MD5(company_email), 1, 8), '@test.com'),
				prefered_email = CONCAT(SUBSTRING(MD5(prefered_email), 1, 8), '@test.com'),
				cell_number = SUBSTRING(CAST(SHA(cell_number) AS CHAR), 1, 10),
				current_address = SUBSTRING(MD5(current_address), 1, 8),
				permanent_address = SUBSTRING(MD5(permanent_address), 1, 8),
				ais_sin_no = SUBSTRING(MD5(ais_sin_no), 1, 8),
				person_to_be_contacted = SUBSTRING(MD5(person_to_be_contacted), 1, 8),
				emergency_phone_number = SUBSTRING(CAST(SHA(emergency_phone_number) AS CHAR), 1, 10),
				user_id = CONCAT(SUBSTRING(MD5(user_id), 1, 8), '@test.com'),
				reports_to = MD5(reports_to),
				expense_approver = CONCAT(SUBSTRING(MD5(expense_approver), 1, 8), '@test.com'),
				shift_request_approver = CONCAT(SUBSTRING(MD5(shift_request_approver), 1, 8), '@test.com'),
				leave_approver = CONCAT(SUBSTRING(MD5(leave_approver), 1, 8), '@test.com'),
				pan_number = SUBSTRING(MD5(pan_number), 1, 8),
				bank_name = SUBSTRING(MD5(bank_name), 1, 8),
				bank_ac_no = SUBSTRING(CAST(SHA(bank_ac_no) AS CHAR), 1, 10),
				ifsc_code = SUBSTRING(MD5(ifsc_code), 1, 8),
				micr_code = SUBSTRING(MD5(micr_code), 1, 8),
				ais_bank_transit = SUBSTRING(CAST(SHA(ais_bank_transit) AS CHAR), 1, 5),
				ais_bank_institution = SUBSTRING(MD5(ais_bank_institution), 1, 3),
				iban = SUBSTRING(MD5(iban), 1, 8),
				passport_number = SUBSTRING(MD5(passport_number), 1, 8),
				bio = SUBSTRING(MD5(bio), 1, 8)
			WHERE 
				employee.name in ({employee_sql})
		""")
		current_offset += 1000
	print("Employees scrubd successfully")

def scrub_clockin_log():
	max_offset = frappe.db.sql("""
					SELECT
						COUNT(clockin_log.name) AS total
					FROM
						`tabClockin Log` AS clockin_log
					""", as_dict=1)[0].total;
	
	current_offset = 0
	while current_offset < max_offset:
		logs = frappe.db.sql(f"""
			SELECT 
				clockin_log.name 
			FROM 
				`tabClockin Log` AS clockin_log
			ORDER BY 
				clockin_log.creation
			LIMIT 1000
			OFFSET {current_offset}
		""", as_dict=1)
	
		clockin_logs = ""
		for row in logs:
			clockin_logs += f"'{row.name}',"
		clockin_logs = clockin_logs[:-1]
		
		frappe.db.sql(f"""
			UPDATE `tabClockin Log` clockin_log
			SET
				clockin_log.user = CONCAT(SUBSTRING(MD5(clockin_log.user), 1, 8), '@test.com')
			WHERE
				clockin_log.name in ({clockin_logs})
		""")
		current_offset += 1000
	print("Clockin Logs scrubd successfully")

def scrub_checkin_request_modification():
	max_offset = frappe.db.sql("""
					SELECT
						COUNT(checkin_request_modification.name) AS total
					FROM
						`tabCheckin Request Modification` AS checkin_request_modification
					""", as_dict=1)[0].total;
	
	current_offset = 0
	while current_offset < max_offset:
		modifications = frappe.db.sql(f"""
			SELECT 
				checkin_request_modification.name 
			FROM 
				`tabCheckin Request Modification` AS checkin_request_modification
			ORDER BY 
				checkin_request_modification.creation
			LIMIT 1000
			OFFSET {current_offset}
		""", as_dict=1)
	
		checkin_request_modifications = ""
		for row in modifications:
			checkin_request_modifications += f"'{row.name}',"
		checkin_request_modifications = checkin_request_modifications[:-1]
		
		frappe.db.sql(f"""
			UPDATE `tabCheckin Request Modification` checkin_request_modification
			SET
				checkin_request_modification.user = CONCAT(SUBSTRING(MD5(checkin_request_modification.user), 1, 8), '@test.com')
			WHERE
				checkin_request_modification.name in ({checkin_request_modifications})
		""")
		current_offset += 1000
	print("Checkin Request Modifications scrubd successfully")

def scrub_user_permission():
	max_offset = frappe.db.sql("""
					SELECT
						COUNT(user_permission.name) AS total
					FROM
						`tabUser Permission` AS user_permission
					""", as_dict=1)[0].total;
	
	current_offset = 0
	while current_offset < max_offset:
		permissions = frappe.db.sql(f"""
			SELECT 
				user_permission.name 
			FROM 
				`tabUser Permission` AS user_permission
			ORDER BY 
				user_permission.creation
			LIMIT 1000
			OFFSET {current_offset}
		""", as_dict=1)
	
		user_permissions = ""
		for row in permissions:
			user_permissions += f"'{row.name}',"
		user_permissions = user_permissions[:-1]
		
		frappe.db.sql(f"""
			UPDATE `tabUser Permission` user_permission
			SET
				user_permission.user = CONCAT(SUBSTRING(MD5(user_permission.user), 1, 8), '@test.com')
			WHERE
				user_permission.name in ({user_permissions})
		""")
		current_offset += 1000
	print("User Permissions scrubd successfully")

def scrub_employee_from_user_permission():
	max_offset = frappe.db.sql("""
					SELECT
						COUNT(user_permission.name) AS total
					FROM
						`tabUser Permission` AS user_permission
					WHERE
						user_permission.allow = 'Employee'
					""", as_dict=1)[0].total;
	
	current_offset = 0
	while current_offset < max_offset:
		permissions = frappe.db.sql(f"""
			SELECT 
				user_permission.name 
			FROM 
				`tabUser Permission` AS user_permission
			WHERE
				user_permission.allow = 'Employee'
			ORDER BY 
				user_permission.creation
			LIMIT 1000
			OFFSET {current_offset}
		""", as_dict=1)
	
		user_permissions = ""
		for row in permissions:
			user_permissions += f"'{row.name}',"
		user_permissions = user_permissions[:-1]
		
		frappe.db.sql(f"""
			UPDATE `tabUser Permission` user_permission
			SET
				user_permission.for_value = MD5(user_permission.for_value)
			WHERE
				user_permission.name in ({user_permissions})
		""")
		current_offset += 1000
	print("Employee User Permissions scrubd successfully")

def scrub_route_history():
	max_offset = frappe.db.sql("""
					SELECT
						COUNT(route_history.name) AS total
					FROM
						`tabRoute History` AS route_history
					""", as_dict=1)[0].total
	current_offset = 0
	while current_offset < max_offset:
		users = frappe.db.sql(f"""
			SELECT 
				route_history.name 
			FROM 
				`tabRoute History` AS route_history
			ORDER BY 
				route_history.creation
			LIMIT 1000
			OFFSET {current_offset}
		""", as_dict=1)
	
		user_sql = ""
		for row in users:
			row_name = row.name.replace("'", "''")
			user_sql += "'" + row_name + "',"
		user_sql = user_sql[:-1]
		
		frappe.db.sql(f"""
			UPDATE `tabRoute History` route_history SET 
				user = CONCAT(SUBSTRING(MD5(route_history.user), 1, 8), '@test.com')
			WHERE 
				route_history.name in ({user_sql})
		""")
		current_offset += 1000
	print("Route history scrubd successfully")

def scrub_activity_log():
	max_offset = frappe.db.sql("""
					SELECT
						COUNT(activity_log.name) AS total
					FROM
						`tabActivity Log` AS activity_log
					""", as_dict=1)[0].total;
	
	current_offset = 0
	while current_offset < max_offset:
		users = frappe.db.sql(f"""
			SELECT 
				activity_log.name 
			FROM 
				`tabActivity Log` AS activity_log
			ORDER BY 
				activity_log.creation
			LIMIT 1000
			OFFSET {current_offset}
		""", as_dict=1)
	
		user_sql = ""
		for row in users:
			row_name = row.name.replace("'", "''")
			user_sql += "'" + row_name + "',"
		user_sql = user_sql[:-1]
		
		frappe.db.sql(f"""
			UPDATE `tabActivity Log` activity_log SET 
				user = CONCAT(SUBSTRING(MD5(activity_log.user), 1, 8), '@test.com'),
				full_name = SUBSTRING(MD5(activity_log.full_name), 1, 8)
			WHERE 
				activity_log.name in ({user_sql})
		""")
		current_offset += 1000
	print("Activity Log scrubd successfully")

def scrub_access_log():
	max_offset = frappe.db.sql("""
					SELECT
						COUNT(access_log.name) AS total
					FROM
						`tabAccess Log` AS access_log
					""", as_dict=1)[0].total;
	
	current_offset = 0
	while current_offset < max_offset:
		users = frappe.db.sql(f"""
			SELECT 
				access_log.name 
			FROM 
				`tabAccess Log` AS access_log
			ORDER BY 
				access_log.creation
			LIMIT 1000
			OFFSET {current_offset}
		""", as_dict=1)
	
		user_sql = ""
		for row in users:
			row_name = row.name.replace("'", "''")
			user_sql += "'" + row_name + "',"
		user_sql = user_sql[:-1]
		
		frappe.db.sql(f"""
			UPDATE `tabAccess Log` access_log SET 
				user = CONCAT(SUBSTRING(MD5(access_log.user), 1, 8), '@test.com')
			WHERE 
				access_log.name in ({user_sql})
		""")
		current_offset += 1000
	print("Access Log scrubd successfully")

def scrub_user():
	max_offset = frappe.db.sql("""
					SELECT
						COUNT(user.name) AS total
					FROM
						`tabUser` AS user
					""", as_dict=1)[0].total;
	
	current_offset = 0
	while current_offset < max_offset:
		users = frappe.db.sql(f"""
			SELECT 
				user.name 
			FROM 
				`tabUser` AS user
			WHERE
				user.name <> 'Administrator'
			ORDER BY 
				user.creation
			LIMIT 1000
			OFFSET {current_offset}
		""", as_dict=1)
	
		user_sql = ""
		for row in users:
			row_name = row.name.replace("'", "''")
			user_sql += "'" + row_name + "',"
		user_sql = user_sql[:-1]
		
		frappe.db.sql(f"""
			UPDATE `tabUser` user SET 
				first_name = SUBSTRING(MD5(first_name), 1, 8),
				middle_name = SUBSTRING(MD5(middle_name), 1, 8),
				last_name = SUBSTRING(MD5(last_name), 1, 8),
				name = CONCAT(SUBSTRING(MD5(name), 1, 8), '@test.com'),
				username = SUBSTRING(MD5(username), 1, 8),
				full_name = CONCAT(first_name, ' ', last_name),
				email = CONCAT(SUBSTRING(MD5(email), 1, 8), '@test.com'),
				phone = SUBSTRING(CAST(SHA(phone) AS CHAR), 1, 5),
				interest = SUBSTRING(MD5(interest), 1, 8),
				bio = SUBSTRING(MD5(bio), 1, 8),
				mobile_no = SUBSTRING(CAST(SHA(mobile_no) AS CHAR), 1, 5),
				email_signature = SUBSTRING(MD5(email_signature), 1, 8)
			WHERE 
				user.name in ({user_sql})
		""")
		current_offset += 1000
	print("Users scrubd successfully")