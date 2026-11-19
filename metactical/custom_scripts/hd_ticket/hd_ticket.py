import frappe
from frappe import _
from frappe.email.email_body import get_message_id
from helpdesk.helpdesk.doctype.hd_ticket.hd_ticket import HDTicket
from helpdesk.utils import capture_event


class CustomHDTicket(HDTicket):
	@frappe.whitelist()
	def reply_via_agent(self, message: str, cc: str = None, bcc: str = None, attachments=None):
		if attachments is None:
			attachments = []

		skip_email_workflow = self.skip_email_workflow()
		medium = "" if skip_email_workflow else "Email"
		subject = f"Re: {self.subject} (#{self.name})"
		sender = frappe.session.user
		recipients = self.raised_by
		sender_email = None if skip_email_workflow else self.sender_email()
		last_communication = self.get_last_communication()

		if last_communication:
			cc = cc or last_communication.cc
			bcc = bcc or last_communication.bcc

		if recipients == "Administrator":
			admin_email = frappe.get_value("User", "Administrator", "email")
			recipients = admin_email

		# Set message_id on the Communication so Frappe can resolve the
		# customer's reply In-Reply-To header directly against this record,
		# rather than falling back to the EmailQueue lookup (which is less
		# reliable once the queue entry ages out).
		msg_id = get_message_id()

		communication = frappe.get_doc(
			{
				"bcc": bcc,
				"cc": cc,
				"communication_medium": medium,
				"communication_type": "Communication",
				"content": message,
				"doctype": "Communication",
				"email_account": sender_email.name if sender_email else None,
				"email_status": "Open",
				"message_id": msg_id,
				"recipients": recipients,
				"reference_doctype": "HD Ticket",
				"reference_name": self.name,
				"sender": sender,
				"sent_or_received": "Sent",
				"status": "Linked",
				"subject": subject,
			}
		)

		communication.insert(ignore_permissions=True)
		capture_event("agent_replied")

		if skip_email_workflow:
			return

		if not sender_email:
			frappe.throw(_("Can not send email. No sender email set up!"))

		_attachments = []

		for attachment in attachments:
			file_doc = frappe.get_doc("File", attachment)
			file_doc.attached_to_name = communication.name
			file_doc.attached_to_doctype = "Communication"
			file_doc.save(ignore_permissions=True)
			_attachments.append({"file_url": file_doc.file_url})

		reply_to_email = sender_email.email_id
		template = (
			"new_reply_on_customer_portal_notification"
			if self.via_customer_portal
			else None
		)
		args = {
			"message": message,
			"portal_link": self.portal_uri,
			"ticket_id": self.name,
		}
		send_delayed = True
		send_now = False

		if self.instantly_send_email():
			send_delayed = False
			send_now = True

		try:
			frappe.sendmail(
				args=args,
				attachments=_attachments,
				bcc=bcc,
				cc=cc,
				communication=communication.name,
				delayed=send_delayed,
				expose_recipients="header",
				message=message,
				message_id=msg_id,
				now=send_now,
				recipients=recipients,
				reference_doctype="HD Ticket",
				reference_name=self.name,
				reply_to=reply_to_email,
				sender=reply_to_email,
				subject=subject,
				template=template,
				with_container=False,
			)
		except Exception as e:
			frappe.throw(_(e))
