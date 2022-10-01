# Copyright (c) 2022, Techlift Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import get_url

class EmployeeSignUpInvitation(Document):
	def submit(self):
		from email.utils import formataddr
		from frappe.core.doctype.communication.email import _make as make_communication
		subject = 'Invite to register for Metactical management system'
		
		recipients = [self.email]
		if not (recipients or cc or bcc):
			return

		sender = None
		default_email = frappe.db.get_value('Email Account', {'default_outgoing': 1}, ['email_id', 'name'], as_dict=1)
		if len(default_email) > 0:
			sender = formataddr((default_email.name, default_email.email_id))
		
		message = 'You\'ve been invited to register at Metactical. Please follow the link below: <br><br> \
					<a href="{0}" >{0}</a>'.format(get_url("/employee-sign-up?new=1&uemail={}".format(self.email)))
		
		if sender is not None:
			frappe.sendmail(recipients = recipients,
				subject = subject,
				sender = sender,
				message = message,
				reference_doctype = self.doctype,
				reference_name = self.name,
				expose_recipients="header")

			# Add mail notification to communication list
			# No need to add if it is already a communication.
			make_communication(
				doctype=self.doctype,
				name=self.name,
				content=message,
				subject=subject,
				sender=sender,
				recipients=recipients,
				communication_medium="Email",
				send_email=False,
				communication_type='Automated Message',
			)
