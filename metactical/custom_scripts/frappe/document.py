import frappe
import json
from frappe import _, msgprint, is_whitelisted

def execute_action(doctype, name, action, **kwargs):
	"""Execute an action on a document (called by background worker)"""
	doc = frappe.get_doc(doctype, name)
	doc.unlock()
	try:
		doc.update({"ais_queue_status": "Not Queued"})
		getattr(doc, action)(**kwargs)
	except Exception:
		frappe.db.rollback()

		# add a comment (?)
		if frappe.local.message_log:
			msg = json.loads(frappe.local.message_log[-1]).get('message')
		else:
			msg = '<pre><code>' + frappe.get_traceback() + '</pre></code>'

		doc.add_comment('Comment', _('Action Failed') + '<br><br>' + msg)
		doc.update({'ais_queue_failed': 1, 'ais_queue_status': "Failed"})
		doc.save()
		doc.notify_update()
