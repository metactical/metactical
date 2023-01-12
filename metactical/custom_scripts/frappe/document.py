import frappe
import json
from frappe import _, msgprint, is_whitelisted
from frappe.utils import nowdate, getdate, now_datetime, file_lock, get_url
from datetime import timedelta

def execute_action(doctype, name, action, **kwargs):
	"""Execute an action on a document (called by background worker)"""
	doc = frappe.get_doc(doctype, name)
	doc.unlock()
	try:
		frappe.db.set_value(doctype, name, "ais_queue_status", "Not Queued", update_modified=False)
		getattr(doc, action)(**kwargs)
	except Exception:
		frappe.db.rollback()

		# add a comment (?)
		if frappe.local.message_log:
			msg = json.loads(frappe.local.message_log[-1]).get('message')
		else:
			msg = '<pre><code>' + frappe.get_traceback() + '</pre></code>'

		doc.add_comment('Comment', _('Action Failed') + '<br><br>' + msg)
		frappe.db.set_value(doctype, name, 'ais_queue_failed', 1, update_modified=False)
		frappe.db.set_value(doctype, name, 'ais_queue_status', "Failed", update_modified=False)
		frappe.db.set_value(doctype, name, 'ais_queueu_comment', msg, update_modified=False)
		doc.notify_update()
		email_submitter(doc, True)
		
def clear_queued_docs():
	pos = frappe.db.get_all('Purchase Order', filters={'ais_queue_status': 'Queued', 'docstatus': 0}, 
								fields=["name", 'ais_queued_date', "'Purchase Order' AS doctype" ])
	srs = frappe.db.get_all('Stock Reconciliation', filters={'ais_queue_status': 'Queued', 'docstatus': 0}, 
								fields=['name', 'ais_queued_date', "'Stock Reconciliation' AS doctype"])
	pis = frappe.db.get_all('Purchase Invoice', filters={'ais_queue_status': 'Queued', 'docstatus': 0}, 
								fields=['name', 'ais_queued_date', "'Purchase Invoice' AS doctype"])
	prs = frappe.db.get_all('Purchase Receipt', filters={'ais_queue_status': 'Queued', 'docstatus': 0}, 
								fields=['name', 'ais_queued_date', "'Purchase Receipt' AS doctype"])
	docs = pos + srs + pis + prs
	for entry in docs:
		if entry.get('ais_queued_date') is not None:
			exp_time = entry.ais_queued_date + timedelta(minutes=15)
			if exp_time < now_datetime():
				doc = frappe.get_doc(entry.doctype, entry.name)
				if file_lock.lock_exists(doc.get_signature()):
					doc.unlock()
					email_submitter(doc)
					
def email_submitter(doc, failed=False):
	from email.utils import formataddr
	from frappe.core.doctype.communication.email import _make as make_communication
	if doc.ais_queued_by is None or doc.ais_queued_by == '' or doc.ais_queued_by == 'Administrator':
		return
		
	subject = 'ERP Document Queue Notification'
	
	recipients = [doc.ais_queued_by]
	if not (recipients or cc or bcc):
		return

	sender = None
	default_email = frappe.db.get_value('Email Account', {'default_outgoing': 1}, ['email_id', 'name'], as_dict=1)
	if len(default_email) > 0:
		sender = formataddr((default_email.name, default_email.email_id))
	
	url = "/app/{0}/{1}".format(doc.doctype.lower().replace(" ", "-"), doc.name)
	message = 'A document you submitted has taken too long and has been unquequd. Please resubmit the document and notify the system \
					administrator <a href="{0}" >{1}</a>'.format(get_url(url), doc.name)
	
	if failed:
		message = 'A document you submitted has failed. Please see the error in the comment section of the document and fix it \
					<a href="{0}">{1}</a>'.format(get_url(url), doc.name)
	
	if sender is not None:
		frappe.sendmail(recipients = recipients,
			subject = subject,
			sender = sender,
			message = message,
			reference_doctype = doc.doctype,
			reference_name = doc.name,
			expose_recipients="header")

		# Add mail notification to communication list
		# No need to add if it is already a communication.
		make_communication(
			doctype=doc.doctype,
			name=doc.name,
			content=message,
			subject=subject,
			sender=sender,
			recipients=recipients,
			communication_medium="Email",
			send_email=False,
			communication_type='Automated Message',
		)

def test_email():
	doc = frappe.get_doc('Purchase Receipt', 'MAT-PRE-2022-00002')
	email_submitter(doc, True)
