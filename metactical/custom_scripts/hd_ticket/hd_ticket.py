import email.utils
import re
import frappe
from frappe import _
from helpdesk.helpdesk.doctype.hd_ticket.hd_ticket import HDTicket
from helpdesk.utils import capture_event


def _clean_subject(subject: str) -> str:
    """Strip accumulated 'Re:' prefixes and '(#xxx)' ticket tags."""
    subject = re.sub(r"^(Re:\s*)+", "", subject, flags=re.IGNORECASE)
    subject = re.sub(r"\s*\(#[^)]+\)", "", subject)
    return subject.strip()


def inject_in_reply_to_on_email_queue(doc, method):
    """before_insert hook for Email Queue.

    Frappe's native in_reply_to→email_queue path never sets In-Reply-To:
    email_queue.py expects Communication.message_id stored with angle brackets,
    but receive.py strips them, so get_string_between always returns empty.
    We work around by carrying the value in frappe.flags and injecting it into
    the MIME message string before the EmailQueue document is saved.
    """
    in_reply_to = getattr(frappe.flags, "hd_ticket_in_reply_to", None)
    if not in_reply_to or not doc.message:
        return
    if "In-Reply-To:" in doc.message:
        return
    # Frappe builds MIME with SMTP policy (CRLF line endings). Try CRLF first,
    # fall back to LF for any normalised storage.
    if "\r\n\r\n" in doc.message:
        sep = "\r\n\r\n"
        new_header = f"\r\nIn-Reply-To: {in_reply_to}"
    elif "\n\n" in doc.message:
        sep = "\n\n"
        new_header = f"\nIn-Reply-To: {in_reply_to}"
    else:
        return
    pos = doc.message.find(sep)
    doc.message = (
        doc.message[:pos]
        + new_header
        + doc.message[pos:]
    )
    frappe.flags.hd_ticket_in_reply_to = None


class CustomHDTicket(HDTicket):
	@frappe.whitelist()
	def reply_via_agent(self, message: str, cc: str = None, bcc: str = None, attachments=None):
		if attachments is None:
			attachments = []

		skip_email_workflow = self.skip_email_workflow()
		medium = "" if skip_email_workflow else "Email"
		subject = f"Re: {_clean_subject(self.subject)} (#{self.name})"
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

		# Use the sender email's domain (e.g. metactical.com) so the Message-Id
		# is a valid FQDN. frappe.local.site is the bench directory name
		# (e.g. "metactical"), which is not a FQDN — Gmail will not set
		# In-Reply-To on replies to emails with bare-hostname Message-Ids,
		# breaking all ticket threading.
		# Frappe's threading lookup strips angle brackets (receive.py), so store bare.
		msg_domain = sender_email.email_id.split("@")[1] if sender_email else frappe.local.site
		msg_id = email.utils.make_msgid(domain=msg_domain).strip("<>")

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
		# Build In-Reply-To from the last communication in this thread so the
		# outgoing email is properly chained in Gmail (and other clients).
		# Frappe stores message_ids without angle brackets; re-wrap for the header.
		in_reply_to = None
		if last_communication and last_communication.message_id:
			in_reply_to = f"<{last_communication.message_id.strip('<>')}>"

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

		# Set flag so inject_in_reply_to_on_email_queue hook can inject
		# In-Reply-To into the MIME message during EmailQueue.before_insert.
		if in_reply_to:
			frappe.flags.hd_ticket_in_reply_to = in_reply_to

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
			frappe.flags.hd_ticket_in_reply_to = None
			frappe.log_error(frappe.get_traceback(), "HD Ticket reply_via_agent sendmail error")
			frappe.throw(_(str(e)))
