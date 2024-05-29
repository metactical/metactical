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
	print("Delivery notes scubd successfully")

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
	print("Payment Entries scubd successfully")
		
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
	print("Sales Orders scubd successfully")

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
	print("Sales Invoices scubd successfully")

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
	print("Pick Lists scubd successfully")

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
	print("Contacts scubd successfully")

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
	print("Addresses scubd successfully")

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
	print("Customers scubd successfully")
