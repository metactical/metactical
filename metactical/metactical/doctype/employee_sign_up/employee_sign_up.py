# Copyright (c) 2022, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from email.utils import formataddr

class EmployeeSignUp(Document):
	def on_submit(self):
		self.validate_sin_mail()
		self.create_user()
		self.create_employee()
		self.send_welcome_mail_to_user()
		
	def validate_sin_mail(self):
		if not self.company_email or self.company_email == "":
			frappe.throw("Please enter a company email address")
		user_exists = frappe.db.exists('User', self.company_email)
		if user_exists:
			frappe.throw('A user already exists with the email {}'.format(self.company_email))
		
		if self.sin_no and self.sin_no != "":
			sin_exists = frappe.db.exists('Employee', {'ais_sin_no': self.sin_no})
			if sin_exists:
				frappe.throw('An employee already exists with the SIN No. {}'.format(self.sin_no))
		
	def create_user(self):
		user = frappe.new_doc('User')
		user.update({
			'email': self.company_email,
			'first_name': self.first_name,
			'last_name': self.last_name,
			'role_profile_name': self.role_profile_name,
			'send_welcome_email': 0,
			'birth_date': self.date_of_birth,
			'phone': self.phone_no,
			'location': self.city + ', ' + self.country,
			'bio': self.comments
		})
		for row in self.roles:
			user.append('roles', {
				'role': row.role
			})
		user.insert(ignore_permissions=True)
		
	def create_employee(self):
		address = self.address1 + "<br>"
		if self.address2 and self.address2 != "":
			address += self.address2 + "<br>"

		state = self.state if self.state else ""
		zip_code = self.zip_code if self.zip_code else ""

		address += self.city + ", " + state + "<br>" + zip_code + "<br>" + self.country
		employee = frappe.new_doc('Employee')
		employee.update({
			'first_name': self.first_name,
			'last_name': self.last_name,
			'gender': self.gender,
			'status': 'Active',
			'date_of_birth': self.date_of_birth,
			'date_of_joining': self.hire_date,
			'ais_sin_no': self.sin_no,
			'ais_sin_expiry': self.sin_expiry_date,
			'ais_bank_transit': self.bank_transit_no,
			'ais_bank_institution': self.bank_institution_no,
			'bank_ac_no': self.bank_account_no,
			'cell_number': self.phone_no,
			'personal_email': self.personal_email,
			'company_email': self.company_email, 
			'user_id': self.company_email,
			'create_user_permission': 1,
			'permanent_address': address,
			'ais_state': self.state,
			'branch': self.branch,
			'bio': self.comments, 
			"bank_document": self.bank_document,
			"person_to_be_contacted": self.emergency_contact_name if self.emergency_contact_name else "",
			"emergency_phone_number": self.emergency_phone if self.emergency_phone else "",
			"relation": self.relation if self.relation else ""
		})
		employee.insert(ignore_permissions=True)
		
	def send_welcome_mail_to_user(self):
		from frappe.utils import get_url
		user = frappe.get_doc('User', self.company_email)
		link = user.reset_password()
		subject = "Welcome to Metactical"
		method = frappe.get_hooks("welcome_email")
		if method:
			subject = frappe.get_attr(method[-1])()
		self.send_login_mail(subject, "new_user",
				dict(
					link=link,
					site_url=get_url(),
				))
				
	def send_login_mail(self, subject, template, add_args, now=None):
		"""send mail with login details"""
		from frappe.utils.user import get_user_fullname
		from frappe.utils import get_url

		created_by = get_user_fullname(frappe.session['user'])
		if created_by == "Guest":
			created_by = "Administrator"

		args = {
			'first_name': self.first_name or self.last_name or "user",
			'user': self.company_email,
			'title': subject,
			'login_url': get_url(),
			'created_by': created_by
		}

		args.update(add_args)
		
		sender = None
		default_email = frappe.db.get_value('Email Account', {'default_outgoing': 1}, ['email_id', 'name'], as_dict=1)
		if len(default_email) > 0:
			sender = formataddr((default_email.name, default_email.email_id))

		frappe.sendmail(recipients=self.personal_email, sender=sender, subject=subject,
			template=template, args=args, header=[subject, "green"],
			delayed=(not now) if now!=None else self.flags.delay_emails, retry=3)
