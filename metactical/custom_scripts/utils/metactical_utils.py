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
	frappe.db.set_value(self.doctype, self.name, 'ais_queue_failed', 0,  update_modified=False)
	frappe.db.set_value(self.doctype, self.name, 'ais_queueu_comment', '',  update_modified=False)
	frappe.db.set_value(self.doctype, self.name, 'ais_queued_date', now_datetime(),  update_modified=False)
	frappe.db.set_value(self.doctype, self.name, 'ais_queued_by', frappe.session.user,  update_modified=False)
	self.lock()
	enqueue('metactical.custom_scripts.frappe.document.execute_action', doctype=self.doctype, name=self.name,
		action=action, **kwargs)
		
def post_to_rocket_chat(doc, msg, failed=False):
	try:
		rocket_chat_settings = frappe.get_single('Rocket Chat Settings')
		if not rocket_chat_settings.rocket_notification:
			return

		channel_name = rocket_chat_settings.channel_name
		headers = {
			'Content-type': rocket_chat_settings.content_type or 'application/json',
			'X-Auth-Token': rocket_chat_settings.auth_token,
			'X-User-Id': rocket_chat_settings.user_id
		}

		url = "/app/{0}/{1}".format(doc.doctype.lower().replace(" ", "-"), doc.name)
		message = 'A document you submitted has taken too long and has been unquequd. Please resubmit the document and notify the system \
						administrator \n[{0}]({1})'.format(get_url(url), get_url(url))
		
		if failed:
			message = 'A document you submitted has failed. Please see the error in the comment section of the document and fix it \
						\n[{0}]({1})'.format(get_url(url), get_url(url))

		payload = {
			'channel': "#"+channel_name,
			'text': message
		}

		response = requests.post(rocket_chat_settings.url, 
								headers=headers, 
								data=json.dumps(payload))

		if response.status_code == 200:
			pass
		else:
			frappe.log_error(title='Rocket Chat Error', message=response.json())
	except Exception as e:
		frappe.log_error(title='Rocket Chat Error', message=frappe.get_traceback())

def format_json_for_html(data, indent_size=2):
	try:
		# Function to recursively format JSON
		def format_json(data, indent_level):
			lines = []
			for key, value in data.items():
				if isinstance(value, dict):
					# Recursively format nested objects
					lines.append(f'{" " * indent_level * indent_size}"{key}": {{ <br>')
					lines.extend(format_json(value, indent_level + 1))
					lines.append(f'{" " * indent_level * indent_size}}}, <br>')
				elif isinstance(value, list):
					# Handle lists of objects
					lines.append(f'{" " * indent_level * indent_size}"{key}": [ <br>')
					for item in value:
						lines.extend(format_json(item, indent_level + 1))
					lines.append(f'{" " * indent_level * indent_size}] <br>')
				else:
					# Format primitive types (string, number, etc.)
					lines.append(f'{" " * indent_level * indent_size}"{key}": "{value}", <br>')
			return lines
		
		# Start formatting from the top-level object
		formatted_lines = format_json(data, indent_level=1)
		
		# Join all lines with newline characters
		formatted_json = '\n'.join(formatted_lines)
		
		return formatted_json
	
	except json.JSONDecodeError as e:
		return f"Error decoding JSON: {str(e)}"
	except Exception as e:
		return f"Error: {str(e)}"

def create_usaepay_log(doctype, docname, action):
	# Create USAePay Log
	log = frappe.get_doc({
		"doctype": "USAePay Log",
		"date": frappe.utils.now(),
		"reference_docname": docname,
		"action": action,
		"reference_doctype": doctype
	}).insert()

	return log

@frappe.whitelist()
def get_customer_payment_information(customer):
	from metactical.custom_scripts.usaepay.usaepay_api import get_token_hash

	# get existing credit card tokens
	tokens = []
	
	if frappe.db.exists("Customer CC", customer):
		tokens = frappe.get_list("Customer CC Tokens", {"parent": customer}, ["name", "label", "token", "cc_number"])

	payment_form_url = frappe.db.get_single_value("Metactical Settings", "payment_form_url")
	billing_address = get_customer_address(customer)

	metactical_settings = frappe.get_single("Metactical Settings")
	form_hash = get_token_hash(metactical_settings, "1234")
	# form_hash = form_hash[6:] if form_hash else None
	
	if not form_hash:
		frappe.log_error(title="Metactical Settings Error", message="Failed to generate form hash. Please add usaepay key and secret")
		frappe.throw(_("Failed to generate form hash. Please check the MetaTactical settings"))

	frappe.response["tokens"] = tokens
	frappe.response["payment_form_url"] = payment_form_url
	frappe.response["address"] = billing_address
	frappe.response["hash"] = form_hash

def get_customer_address(customer):
	addresses = frappe.db.sql("""SELECT
			address_line1, address_line2, city, state, 
			country, phone, company, pincode, 
			phone, address_type, 
			is_shipping_address, is_primary_address
		FROM
			`tabAddress`
		JOIN
			`tabDynamic Link` ON `tabDynamic Link`.parent = `tabAddress`.name
		WHERE
			`tabDynamic Link`.link_doctype = 'Customer' AND
			`tabDynamic Link`.link_name = %(customer)s 
		""", {"customer": customer}, as_dict=1)

	grouped_address = {}
	billing_address = None
	shipping_address = None
	for address in addresses:
		if billing_address and shipping_address:
			break

		if address.get("is_primary_address"):
			billing_address = address
		elif address.get("is_shipping_address"):
			shipping_address = address

		if address.address_type not in grouped_address:
			grouped_address[address.address_type] = []

		grouped_address[address.address_type].append(address)
		
	if not billing_address:
		billing_address = grouped_address["Billing"][0] if "Billing" in grouped_address else None

	if not shipping_address:
		shipping_address = grouped_address["Shipping"][0] if "Shipping" in grouped_address else None
	
	# add customer personal information to the address
	customer_info = frappe.db.get_value("Customer", customer, ["ais_company", "first_name", "last_name"], as_dict=1)
	if customer_info:
		billing_address.update(customer_info) if billing_address else None
		shipping_address.update(customer_info) if shipping_address else None

	return {
		"billing": billing_address,
		"shipping": shipping_address
	}

	