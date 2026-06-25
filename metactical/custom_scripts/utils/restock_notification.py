# Copyright (c) 2026, Storebuilder Commerce Inc and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import now_datetime

# Restock Email Log delivery statuses we set from this flow.
STATUS_QUEUED = "Queued"   # log created, email not sent
STATUS_SENT = "Sent"       # email handed off to the email queue
STATUS_FAILED = "Failed"   # send attempted but could not be completed


def on_sle_submit(doc, method=None):
	"""Called from CustomStockLedgerEntry.on_submit.

	For the SLE's item, create a Restock Email Log for every subscription that
	doesn't have one yet. Wrapped so a failure here never blocks stock posting.
	"""
	try:
		if not doc.get("item_code"):
			return

		subscriptions = frappe.get_all(
			"Restock Subscription Log",
			filters={"item_code": doc.item_code, "docstatus": ["!=", 2]},
			pluck="name",
		)
		for subscription_name in subscriptions:
			# Isolate each subscription so one failure doesn't skip the rest.
			try:
				process_subscription(subscription_name)
			except Exception:
				frappe.log_error(
					title="Restock Notification: subscription failed",
					message=frappe.get_traceback(),
				)
	except Exception:
		frappe.log_error(
			title="Restock Notification: SLE handler failed",
			message=frappe.get_traceback(),
		)


def process_subscription(subscription_name):
	"""Create the email log for a subscription (once), sending the email only when
	both settings switches are enabled. Returns the email log name, or None if one
	already existed."""
	# Skip if this subscription already produced an email log.
	if frappe.db.exists("Restock Email Log", {"restock_subscription_log": subscription_name}):
		return None

	sub = frappe.get_doc("Restock Subscription Log", subscription_name)
	settings = frappe.get_single("Restock Notification Settings")

	log = frappe.get_doc({
		"doctype": "Restock Email Log",
		"customer_email": sub.customer_email,
		"restock_subscription_log": sub.name,
		"item_code": sub.item_code,
		"lead_source": sub.lead_source,
		"price": get_item_price(sub.item_code),  # price-list rate, or blank if none
		"sent_at": now_datetime(),
		"status": STATUS_QUEUED,
	})
	log.insert(ignore_permissions=True)

	# Send automatically only when notifications are on AND auto-send is on.
	# In every other case we keep the log and leave it for a manual send.
	# An auto-send failure must never break stock posting: keep the log and
	# mark it Failed so it can be retried manually from the Send Email button.
	if settings.send_notification and settings.send_email_automatically:
		try:
			send_log_email(log, settings)
		except Exception:
			log.db_set("status", STATUS_FAILED, update_modified=False)
			frappe.log_error(
				title="Restock Notification: auto-send failed",
				message=frappe.get_traceback(),
			)

	return log.name


def get_item_price(item_code):
	"""Selling price-list rate for the item from the system, or None when no price is set.

	Uses the default selling price list from Selling Settings when configured, otherwise
	falls back to any selling Item Price for the item.
	"""
	price_list = frappe.db.get_single_value("Selling Settings", "selling_price_list")

	filters = {"item_code": item_code, "selling": 1}
	if price_list:
		filters["price_list"] = price_list

	return frappe.db.get_value("Item Price", filters, "price_list_rate")


def get_site_config(lead_source):
	"""Return the Restock Notification Site Config row (email account + template) that
	matches the given lead source, or None."""
	rows = frappe.get_all(
		"Restock Notification Site Config",
		filters={"parenttype": "Restock Notification Settings", "lead_source": lead_source},
		fields=["email", "email_template"],
		limit=1,
	)
	return rows[0] if rows else None


def render_email(log, config):
	"""Render the configured Email Template against the email log. Returns (subject, message)."""
	template = frappe.get_doc("Email Template", config["email_template"])
	context = {
		"doc": log,
		"item_code": log.item_code,
		"customer_email": log.customer_email,
		"lead_source": log.lead_source,
		"price": log.price,
	}
	subject = frappe.render_template(template.subject or "", context)
	body = template.response_html or template.get("response") or ""
	message = frappe.render_template(body, context)
	return subject, message


def send_log_email(log, settings=None):
	"""Queue the restock email for an email log and update its status. Returns True on
	success, False when no template/config is available for the log's lead source."""
	settings = settings or frappe.get_single("Restock Notification Settings")
	config = get_site_config(log.lead_source)

	if not config or not config.get("email_template"):
		frappe.log_error(
			title="Restock Notification: no template configured",
			message=f"No Restock Notification Site Config (email template) for lead source "
			f"'{log.lead_source}' (email log {log.name}).",
		)
		return False

	sender = (
		frappe.db.get_value("Email Account", config["email"], "email_id")
		if config.get("email") else None
	)
	subject, message = render_email(log, config)

	frappe.sendmail(
		recipients=[log.customer_email],
		sender=sender,
		subject=subject,
		message=message,
		reference_doctype="Restock Email Log",
		reference_name=log.name,
	)

	log.db_set({"status": STATUS_SENT, "sent_at": now_datetime()}, update_modified=False)
	return True


@frappe.whitelist()
def get_email_preview(email_log):
	"""Data for the Send Email dialog: rendered subject/body, recipient, and whether
	sending is currently allowed."""
	log = frappe.get_doc("Restock Email Log", email_log)
	settings = frappe.get_single("Restock Notification Settings")
	config = get_site_config(log.lead_source)

	subject, message = ("", "")
	if config and config.get("email_template"):
		subject, message = render_email(log, config)

	return {
		"recipient": log.customer_email,
		"subject": subject,
		"message": message,
		"can_send": bool(settings.send_notification),
		"has_template": bool(config and config.get("email_template")),
	}


@frappe.whitelist()
def send_email(email_log):
	"""Manually send the restock email for an email log (the dialog's Send button)."""
	settings = frappe.get_single("Restock Notification Settings")
	if not settings.send_notification:
		frappe.throw(_("Sending notifications is disabled in Restock Notification Settings."))

	log = frappe.get_doc("Restock Email Log", email_log)
	if not send_log_email(log, settings):
		frappe.throw(
			_("No email template is configured for lead source {0}.").format(log.lead_source or "—")
		)
	return {"status": STATUS_SENT}
