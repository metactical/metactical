# Copyright (c) 2026, Storebuilder Commerce Inc and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import now_datetime

STATUS_PENDING = "Pending"  # auto-send off -> awaiting a (manual) send
STATUS_SENT = "Sent"        # auto-send on -> handed off to the mail service


def create_email_log(sub):
	"""Create the Restock Email Log for a subscription (once). Returns the email log
	name, or None if one already existed for this subscription."""
	if frappe.db.exists("Restock Email Log", {"restock_subscription_log": sub.name}):
		return None

	settings = frappe.get_single("Restock Notification Settings")
	# Resolve the actual Item from the retail SKU suffix on the subscription.
	item_code = get_item_code_from_retail_sku(sub.retail_sku)

	# Created as Pending. If auto-send is on we send it right away through the same
	# path as the manual "Send Email" button, which flips it to Sent and stores the
	# Message-Id. delivery_status stays blank; the mail service fills it in.
	log = frappe.get_doc({
		"doctype": "Restock Email Log",
		"restock_subscription_log": sub.name,
		"customer_email": sub.customer_email,
		"customer_name": sub.customer_name,
		"item_code": item_code,
		"retail_sku": sub.retail_sku,
		"lead_source": sub.lead_source,
		"price": sub.item_price,
		"sent_at": now_datetime(),
		"status": STATUS_PENDING,
	})
	log.insert(ignore_permissions=True)

	if settings.send_email_automatically:

		try:
			send_email(log.name)
		except Exception:
			frappe.log_error(
				title="Restock Notification: auto-send failed",
				message=frappe.get_traceback(),
			)

	return log.name


def get_item_code_from_retail_sku(retail_sku):
	"""Resolve the Item whose RetailSKUSuffix (`ifw_retailskusuffix`) matches, and
	return its item code (the Item name), or None when nothing matches."""
	if not retail_sku:
		return None
	return frappe.db.get_value("Item", {"ifw_retailskusuffix": retail_sku}, "name")


def get_site_config(lead_source):
	"""Return the Restock Notification Site Config row (email account + template) that
	matches the given lead source, or None."""
	rows = frappe.get_all(
		"Restock Notification Site Config",
		filters={"parenttype": "Restock Notification Settings", "lead_source": lead_source},
		fields=["email", "email_template", "replay_email_address"],
		limit=1,
	)
	return rows[0] if rows else None


def render_email(log, config):
	"""Render the configured Email Template against the email log. Returns (subject, message)."""
	template = frappe.get_doc("Email Template", config["email_template"])
	item_name = frappe.db.get_value("Item", log.item_code, "item_name") if log.item_code else None
	context = {
		"doc": log,
		"item_code": log.item_code,
		"item_name": item_name,
		"retail_sku": log.retail_sku,
		"customer_name": log.customer_name,
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

	# sendmail returns the Email Queue doc; its message_id is the Message-Id header
	# (stored without angle brackets) that SendGrid reports back as `smtp-id`.
	queue = frappe.sendmail(
		recipients=[log.customer_email],
		sender=sender,
		reply_to=config.get("replay_email_address") or None,
		subject=subject,
		message=message,
		reference_doctype="Restock Email Log",
		reference_name=log.name,
	)

	values = {"status": STATUS_SENT, "sent_at": now_datetime()}
	message_id = getattr(queue, "message_id", None) if queue else None
	if message_id:
		values["message_id"] = message_id
	log.db_set(values, update_modified=False)
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
