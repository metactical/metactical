import frappe
from frappe.utils import file_lock, now_datetime, get_url
from frappe import _
import requests, json

def queue_action(self, action, **kwargs):
    """Run an action in background. If the action has an inner function,
    like _submit for submit, it will call that instead"""
    # call _submit instead of submit, so you can override submit to call
    # run_delayed based on some action
    # See: Stock Reconciliation
    from frappe.utils.background_jobs import enqueue

    if hasattr(self, '_' + action):
        action = '_' + action

    if file_lock.lock_exists(self.get_signature()):
        frappe.throw(_('This document is currently queued for execution. Please try again'),
            title=_('Document Queued'))
    
    frappe.db.set_value(self.doctype, self.name, 'ais_queue_status', 'Queued',  update_modified=False)
    frappe.db.set_value(self.doctype, self.name, 'ais_queued_date', now_datetime(),  update_modified=False)
    frappe.db.set_value(self.doctype, self.name, 'ais_queued_by', frappe.session.user,  update_modified=False)
    self.lock()
    enqueue('metactical.custom_scripts.frappe.document.execute_action', doctype=self.doctype, name=self.name,
        action=action, **kwargs)
        
def post_to_rocket_chat(doc, msg, failed=False):
    try:
        headers = {
            'Content-type': 'application/json',
            'X-Auth-Token': "KOXg-d6VD2oA4itXY9Ch_dWbSqm-3fYWNQcUtK5s7mT",
            'X-User-Id': "jzu7voEDrRcbKnn27"
        }

        url = "/app/{0}/{1}".format(doc.doctype.lower().replace(" ", "-"), doc.name)
        message = 'A document you submitted has taken too long and has been unquequd. Please resubmit the document and notify the system \
                        administrator \n[{0}]({1})'.format(get_url(url), get_url(url))
        
        if failed:
            message = 'A document you submitted has failed. Please see the error in the comment section of the document and fix it \
                        \n[{0}]({1})'.format(get_url(url), get_url(url))

        payload = {
            'channel': "#ERP-Document-Submission-Errors",
            'text': message
        }

        response = requests.post(f'https://chat.metactical.com/api/v1/chat.postMessage', 
                                headers=headers, 
                                data=json.dumps(payload))

        if response.status_code == 200:
            pass
        else:
            frappe.log_error(title='Rocket Chat Error', message=response.json())
    except Exception as e:
        frappe.log_error(title='Rocket Chat Error', message=frappe.get_traceback())
